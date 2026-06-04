#!/usr/bin/env bash
# who-deleted.sh — 查最近谁删过 ai-costing-system 下的文件 / 目录
#
# 用法:
#   ops/audit/who-deleted.sh              # 默认: 最近 24 小时
#   ops/audit/who-deleted.sh today        # 今天 00:00 起
#   ops/audit/who-deleted.sh 1h           # 最近 1 小时
#   ops/audit/who-deleted.sh 30m          # 最近 30 分钟
#   ops/audit/who-deleted.sh 7d           # 最近 7 天
#   ops/audit/who-deleted.sh raw          # 原始 audit log dump (调试用)
#
# 需要 sudo (audit log 是 root:root 600)。第一次会要密码。
set -euo pipefail

LOGFILE=/var/log/audit/audit.log
SINCE_ARG="${1:-24h}"

case "$SINCE_ARG" in
  raw)
    grep -E '(key="costing_del"|nametype=DELETE)' "$LOGFILE" | tail -200
    exit 0 ;;
  today) SINCE_TS=$(date -d 'today 00:00' +%s) ;;
  *m)    SINCE_TS=$(date -d "${SINCE_ARG%m} minutes ago" +%s) ;;
  *h)    SINCE_TS=$(date -d "${SINCE_ARG%h} hours ago" +%s) ;;
  *d)    SINCE_TS=$(date -d "${SINCE_ARG%d} days ago" +%s) ;;
  *)     echo "unknown window: $SINCE_ARG (try: today / 1h / 30m / 7d / raw)" >&2; exit 2 ;;
esac

echo "查询窗口: 自 $(date -d "@$SINCE_TS" '+%Y-%m-%d %H:%M:%S') 起"
echo "--------------------------------------------------------------------"

# Pair SYSCALL with PATH/CWD records by audit msg id.
awk -v since="$SINCE_TS" '
  /^type=SYSCALL/ && /key="costing_del"/ {
    # extract timestamp and msg id from msg=audit(TS:ID)
    match($0, /audit\(([0-9]+)\.([0-9]+):([0-9]+)\)/, m)
    ts=m[1]; id=m[3]
    if (ts+0 < since) next
    match($0, /pid=([0-9]+)/, p);  pid=p[1]
    match($0, /ppid=([0-9]+)/, pp); ppid=pp[1]
    match($0, /comm="([^"]+)"/, c); comm=c[1]
    match($0, /exe="([^"]+)"/, e);  exe=e[1]
    match($0, /SYSCALL=([a-z0-9]+)/, s); sc=s[1]
    syscall[id]=sc; pids[id]=pid; ppids[id]=ppid; comms[id]=comm; exes[id]=exe; tss[id]=ts
    next
  }
  /type=CWD/ {
    match($0, /audit\([0-9]+\.[0-9]+:([0-9]+)\)/, m); id=m[1]
    if (!(id in syscall)) next
    match($0, /cwd="([^"]+)"/, c); cwds[id]=c[1]
    next
  }
  /type=PATH/ && /nametype=DELETE/ {
    match($0, /audit\([0-9]+\.[0-9]+:([0-9]+)\)/, m); id=m[1]
    if (!(id in syscall)) next
    match($0, /name="([^"]+)"/, np); paths[id]=paths[id] np[1] " "
    next
  }
  /type=PATH/ && /nametype=CREATE/ && /renameat/ {
    match($0, /audit\([0-9]+\.[0-9]+:([0-9]+)\)/, m); id=m[1]
    if (!(id in syscall)) next
    match($0, /name="([^"]+)"/, np); paths[id]=paths[id] "→" np[1] " "
  }
  END {
    cnt=asorti(tss, sorted, "@val_num_asc")
    if (cnt==0) { print "(窗口内无任何删除/重命名事件)"; exit }
    for (i=1; i<=cnt; i++) {
      id=sorted[i]
      ts=tss[id]
      cmd="date -d @" ts " +\"%Y-%m-%d %H:%M:%S\""
      cmd | getline timestr; close(cmd)
      printf "[%s] %-10s pid=%-7s ppid=%-7s exe=%s\n", timestr, syscall[id], pids[id], ppids[id], exes[id]
      printf "    cwd  : %s\n", cwds[id] ? cwds[id] : "(unknown)"
      printf "    target: %s\n\n", paths[id] ? paths[id] : "(unknown)"
    }
    printf "==================================================\n"
    printf "共 %d 条删除/重命名事件\n", cnt
  }
' "$LOGFILE"

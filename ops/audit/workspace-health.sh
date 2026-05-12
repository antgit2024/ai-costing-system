#!/usr/bin/env bash
# workspace-health.sh — 工作区健康检查（"无形删除"主动监测）
#
# 做什么:
#   1. 对比 git index（应该有的文件）vs working tree（实际有的文件）
#   2. 任何 git tracked 但文件不存在的 → MISSING（核心信号）
#   3. 自动 git restore 这些文件（恢复 HEAD 状态）
#   4. 大批量缺失（>= ALERT_THRESHOLD）→ 写 ALERT 文件 + journal 高优先级
#   5. 同时巡检 ops/systemd/user/install.sh --check（user-mode unit 是否还活）
#
# 为什么:
#   - audit 是事后取证，告诉你"谁干的"
#   - 这个是当前健康主动检测，告诉你"现在少不少东西"
#   - 两者互补：少了什么 (此脚本) + 谁删的 (audit)
#
# 用法:
#   ops/audit/workspace-health.sh              # 检查 + 自动 restore + 报警
#   ops/audit/workspace-health.sh --check      # 只检查，不 restore，不报警（你手动跑用）
#   ops/audit/workspace-health.sh --quiet      # 静默模式（cron / timer 用）
set -euo pipefail

ALERT_THRESHOLD=5    # 一次缺失 >=5 个文件 = 可疑批量删除事件
REPO=/home/admin/ai-costing-system
DATA_DIR="$HOME/.local/share/costing-audit"
HEALTH_LOG="$DATA_DIR/workspace-health.log"
ALERT_FILE="$DATA_DIR/HEALTH_ALERT_$(date +%Y%m%d_%H%M%S).txt"
QUIET=0
DRY_RUN=0
case "${1:-}" in
  --check) DRY_RUN=1 ;;
  --quiet) QUIET=1 ;;
esac

mkdir -p "$DATA_DIR"
cd "$REPO"

# 1) git tracked but missing in working tree
MISSING=$(git ls-files --error-unmatch -z 2>/dev/null | xargs -0 -I{} sh -c '[ -e "$1" ] || printf "%s\n" "$1"' _ {} 2>/dev/null || true)
MISSING_COUNT=$(printf "%s" "$MISSING" | grep -c . || true)

# 2) systemd units health (the broken-symlink + vanished-unit case)
UNIT_PROBLEMS=$("$REPO/ops/systemd/user/install.sh" --check 2>&1 | grep -E '^(MISSING|BROKEN)' || true)
UNIT_PROBLEM_COUNT=$(printf "%s" "$UNIT_PROBLEMS" | grep -c . || true)

# 3) Format report
TS=$(date '+%Y-%m-%d %H:%M:%S')
REPORT=$(cat <<EOF
[$TS] workspace-health check
  - tracked-but-missing files: $MISSING_COUNT
  - systemd unit problems    : $UNIT_PROBLEM_COUNT
EOF
)

if [ "$MISSING_COUNT" -gt 0 ]; then
  REPORT="$REPORT

  MISSING FILES:
$(printf '%s\n' "$MISSING" | sed 's/^/    /')"
fi

if [ "$UNIT_PROBLEM_COUNT" -gt 0 ]; then
  REPORT="$REPORT

  UNIT PROBLEMS:
$(printf '%s\n' "$UNIT_PROBLEMS" | sed 's/^/    /')"
fi

# 4) Decide action
if [ "$MISSING_COUNT" -eq 0 ] && [ "$UNIT_PROBLEM_COUNT" -eq 0 ]; then
  [ "$QUIET" -eq 1 ] || echo "[$TS] workspace OK (no missing files, no unit problems)"
  echo "[$TS] OK" >> "$HEALTH_LOG"
  exit 0
fi

# 5) Auto-restore missing files (unless --check)
if [ "$MISSING_COUNT" -gt 0 ] && [ "$DRY_RUN" -eq 0 ]; then
  echo "$MISSING" | xargs -d '\n' -r -I{} git checkout HEAD -- "{}" 2>>"$HEALTH_LOG"
  REPORT="$REPORT

  ACTION: auto-restored $MISSING_COUNT files from HEAD"
fi

# 6) Auto-fix systemd units (unless --check)
if [ "$UNIT_PROBLEM_COUNT" -gt 0 ] && [ "$DRY_RUN" -eq 0 ]; then
  "$REPO/ops/systemd/user/install.sh" >> "$HEALTH_LOG" 2>&1 || true
  REPORT="$REPORT

  ACTION: re-ran ops/systemd/user/install.sh"
fi

# 7) Echo + log
echo "$REPORT" | tee -a "$HEALTH_LOG"

# 8) Loud alert if batch event
TOTAL=$((MISSING_COUNT + UNIT_PROBLEM_COUNT))
if [ "$TOTAL" -ge "$ALERT_THRESHOLD" ]; then
  {
    echo "============================================================"
    echo "WORKSPACE HEALTH ALERT @ $TS"
    echo "============================================================"
    echo "$REPORT"
    echo
    echo "Cross-check the audit log to identify the culprit:"
    echo "  ops/audit/who-deleted.sh 1h"
    echo "  ops/audit/who-deleted.sh today"
  } > "$ALERT_FILE"
  if command -v systemd-cat >/dev/null 2>&1; then
    echo "WORKSPACE HEALTH ALERT: $TOTAL anomalies (see $ALERT_FILE)" \
      | systemd-cat -p alert -t costing-health
  fi
  [ "$QUIET" -eq 1 ] || {
    echo
    echo "!!! ALERT written: $ALERT_FILE"
    echo "!!! Cross-check: ops/audit/who-deleted.sh 1h"
  }
fi

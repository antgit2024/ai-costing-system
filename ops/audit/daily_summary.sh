#!/usr/bin/env bash
# daily_summary.sh — 每天早上汇总过去 24h 在 ai-costing-system 下的删除/重命名事件
# 落地位置: ~/.local/share/costing-audit/summary.log (累积) + 屏幕回显
# 异常时（>= ABNORMAL_THRESHOLD 条事件）额外写一个 ALERT 标记文件
set -euo pipefail

ABNORMAL_THRESHOLD=20  # 24h 内删除超过 20 条文件 = 可疑
DATA_DIR="$HOME/.local/share/costing-audit"
SUMMARY_LOG="$DATA_DIR/summary.log"
ALERT_FILE="$DATA_DIR/ALERT_$(date +%Y%m%d_%H%M%S).txt"
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

mkdir -p "$DATA_DIR"

REPORT="$("$SCRIPT_DIR/who-deleted.sh" 24h 2>&1)"
COUNT=$(echo "$REPORT" | grep -oE '共 [0-9]+ 条' | grep -oE '[0-9]+' || echo 0)
COUNT=${COUNT:-0}

{
  echo
  echo "================================================================"
  echo "Audit Daily Summary @ $(date '+%Y-%m-%d %H:%M:%S')  (window: last 24h)"
  echo "================================================================"
  echo "$REPORT"
} | tee -a "$SUMMARY_LOG"

if [ "$COUNT" -ge "$ABNORMAL_THRESHOLD" ]; then
  {
    echo "ALERT: 过去 24h 在 ai-costing-system 下有 $COUNT 条删除/重命名事件 (阈值 $ABNORMAL_THRESHOLD)"
    echo "时间: $(date '+%Y-%m-%d %H:%M:%S')"
    echo
    echo "$REPORT"
  } > "$ALERT_FILE"
  echo
  echo "!!! 已写报警: $ALERT_FILE"
fi

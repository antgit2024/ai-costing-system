#!/usr/bin/env bash
set -euo pipefail

# Nightly refresh for cached report snapshots.
#
# Usage:
#   BASE_URL="https://<host>/api/planner" ./ops/nightly_refresh_reports.sh
#
# Notes:
# - These endpoints are synchronous today; keep the range small (default 7 days,
#   aligned with the UI default in ProfitInsightsPage v1.4 since 2026-05-12).
# - For per-channel caches, run this script per channel (add channel=...).
# - Auth: 走 require_staff_role 双轨认证的服务账号通道
#   (X-PLANNER-ADMIN-KEY header). 若 .env 里 PLANNER_ADMIN_KEY 为空,
#   后端会落入 "dev-friendly 放行" 分支 (见 dependencies.py:75-82),
#   所以 fallback 任意字符串都能在 dev/staging 上 200; 生产侧一旦配了
#   PLANNER_ADMIN_KEY, 这个 cron 也会自动用上 (因为 systemd service
#   EnvironmentFile=.env 会注入).

BASE_URL="${BASE_URL:-http://127.0.0.1:8800/api/planner}"
RANGE_DAYS="${RANGE_DAYS:-7}"
OPERATOR_ID="${OPERATOR_ID:-cron}"
ADMIN_KEY="${PLANNER_ADMIN_KEY:-ai-costing-internal-cron}"

curl_json() {
  local url="$1"
  echo "[refresh] $url"
  # 失败不拉整个脚本下水: 一个 endpoint 503 不应导致后续 12 个不刷.
  if ! curl -fsS -X POST -H "X-PLANNER-ADMIN-KEY: $ADMIN_KEY" "$url" >/dev/null; then
    echo "[WARN] refresh failed: $url" >&2
  fi
}

# Models summary (profit-by-model list in insights/models)
curl_json "${BASE_URL}/reports/insights/models-summary/refresh?range_days=${RANGE_DAYS}&operator_id=${OPERATOR_ID}"

# Sales profit dashboard (insights/sales)
curl_json "${BASE_URL}/reports/insights/sales-profit-dashboard/refresh?range_days=${RANGE_DAYS}&group_by=day&top_n=12&operator_id=${OPERATOR_ID}"
curl_json "${BASE_URL}/reports/insights/sales-profit-dashboard/refresh?range_days=${RANGE_DAYS}&group_by=week&top_n=12&operator_id=${OPERATOR_ID}"
curl_json "${BASE_URL}/reports/insights/sales-profit-dashboard/refresh?range_days=${RANGE_DAYS}&group_by=month&top_n=12&operator_id=${OPERATOR_ID}"
curl_json "${BASE_URL}/reports/insights/sales-profit-dashboard/refresh?range_days=${RANGE_DAYS}&group_by=day&top_n=100&operator_id=${OPERATOR_ID}"
curl_json "${BASE_URL}/reports/insights/sales-profit-dashboard/refresh?range_days=${RANGE_DAYS}&group_by=week&top_n=100&operator_id=${OPERATOR_ID}"
curl_json "${BASE_URL}/reports/insights/sales-profit-dashboard/refresh?range_days=${RANGE_DAYS}&group_by=month&top_n=100&operator_id=${OPERATOR_ID}"

# After-sales dashboard (insights/after-sales)
curl_json "${BASE_URL}/reports/insights/after-sales-dashboard/refresh?range_days=${RANGE_DAYS}&group_by=day&view=factory&operator_id=${OPERATOR_ID}"
curl_json "${BASE_URL}/reports/insights/after-sales-dashboard/refresh?range_days=${RANGE_DAYS}&group_by=week&view=factory&operator_id=${OPERATOR_ID}"
curl_json "${BASE_URL}/reports/insights/after-sales-dashboard/refresh?range_days=${RANGE_DAYS}&group_by=month&view=factory&operator_id=${OPERATOR_ID}"
curl_json "${BASE_URL}/reports/insights/after-sales-dashboard/refresh?range_days=${RANGE_DAYS}&group_by=day&view=ops&operator_id=${OPERATOR_ID}"
curl_json "${BASE_URL}/reports/insights/after-sales-dashboard/refresh?range_days=${RANGE_DAYS}&group_by=week&view=ops&operator_id=${OPERATOR_ID}"
curl_json "${BASE_URL}/reports/insights/after-sales-dashboard/refresh?range_days=${RANGE_DAYS}&group_by=month&view=ops&operator_id=${OPERATOR_ID}"

# Shops summaries (insights/shops)
curl_json "${BASE_URL}/reports/insights/shops/profit-by-channel/refresh?range_days=${RANGE_DAYS}&group_by=month&operator_id=${OPERATOR_ID}"
curl_json "${BASE_URL}/reports/insights/shops/returns-rate-by-channel/refresh?range_days=${RANGE_DAYS}&group_by=month&operator_id=${OPERATOR_ID}"

# Shipment ledger "issues" snapshot (top 200)
curl_json "${BASE_URL}/reports/shipments/issues/refresh?range_days=${RANGE_DAYS}&limit=200&operator_id=${OPERATOR_ID}"

echo "[done] range_days=${RANGE_DAYS}"


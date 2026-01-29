#!/usr/bin/env bash
set -euo pipefail

# Nightly refresh for cached report snapshots.
#
# Usage:
#   BASE_URL="https://<host>/api/planner" ./ops/nightly_refresh_reports.sh
#
# Notes:
# - These endpoints are synchronous today; keep the range small (default 30 days).
# - For per-channel caches, run this script per channel (add channel=...).

BASE_URL="${BASE_URL:-http://127.0.0.1:8800/api/planner}"
RANGE_DAYS="${RANGE_DAYS:-30}"
OPERATOR_ID="${OPERATOR_ID:-cron}"

curl_json() {
  local url="$1"
  echo "[refresh] $url"
  curl -sS -X POST "$url" >/dev/null
}

# Models summary (profit-by-model list in insights/models)
curl_json "${BASE_URL}/reports/insights/models-summary/refresh?range_days=${RANGE_DAYS}&operator_id=${OPERATOR_ID}"

# Sales profit dashboard (insights/sales)
curl_json "${BASE_URL}/reports/insights/sales-profit-dashboard/refresh?range_days=${RANGE_DAYS}&group_by=week&operator_id=${OPERATOR_ID}"
curl_json "${BASE_URL}/reports/insights/sales-profit-dashboard/refresh?range_days=${RANGE_DAYS}&group_by=month&operator_id=${OPERATOR_ID}"

# After-sales dashboard (insights/after-sales)
curl_json "${BASE_URL}/reports/insights/after-sales-dashboard/refresh?range_days=${RANGE_DAYS}&group_by=week&view=factory&operator_id=${OPERATOR_ID}"
curl_json "${BASE_URL}/reports/insights/after-sales-dashboard/refresh?range_days=${RANGE_DAYS}&group_by=month&view=factory&operator_id=${OPERATOR_ID}"
curl_json "${BASE_URL}/reports/insights/after-sales-dashboard/refresh?range_days=${RANGE_DAYS}&group_by=week&view=ops&operator_id=${OPERATOR_ID}"
curl_json "${BASE_URL}/reports/insights/after-sales-dashboard/refresh?range_days=${RANGE_DAYS}&group_by=month&view=ops&operator_id=${OPERATOR_ID}"

# Shops summaries (insights/shops)
curl_json "${BASE_URL}/reports/insights/shops/profit-by-channel/refresh?range_days=${RANGE_DAYS}&group_by=month&operator_id=${OPERATOR_ID}"
curl_json "${BASE_URL}/reports/insights/shops/returns-rate-by-channel/refresh?range_days=${RANGE_DAYS}&group_by=month&operator_id=${OPERATOR_ID}"

echo "[done] range_days=${RANGE_DAYS}"


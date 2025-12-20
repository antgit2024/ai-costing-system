#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DIST_DIR="${PROJECT_ROOT}/dist"
# 默认对齐生产 Nginx 的 root（/var/www/html/ai-costing/dist），也可通过
# PLANNER_STATIC_DIR 覆盖
TARGET_DIR="${PLANNER_STATIC_DIR:-/var/www/html/ai-costing/dist}"

if [[ ! -d "${DIST_DIR}" ]]; then
  echo "[deploy] dist 目录不存在，请先运行 npm run build" >&2
  exit 1
fi

echo "[deploy] 将 ${DIST_DIR} 内容同步到 ${TARGET_DIR}"
mkdir -p "${TARGET_DIR}"

if command -v rsync >/dev/null 2>&1; then
  rsync -av --delete "${DIST_DIR}/" "${TARGET_DIR}/"
else
  echo "[deploy] rsync 不存在，使用 cp fallback" >&2
  # 简单保护，防止误删根目录
  if [[ "${TARGET_DIR}" == "/" ]]; then
    echo "[deploy] 目标目录异常，终止复制" >&2
    exit 1
  fi
  find "${TARGET_DIR}" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
  cp -a "${DIST_DIR}/." "${TARGET_DIR}/"
fi

echo "[deploy] 完成，静态资源已更新至 ${TARGET_DIR}"















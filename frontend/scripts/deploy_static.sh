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

echo "[deploy] 原子发布：将 ${DIST_DIR} 切换到 ${TARGET_DIR}"

# 简单保护，防止误删根目录
if [[ "${TARGET_DIR}" == "/" ]]; then
  echo "[deploy] 目标目录异常（/），终止部署" >&2
  exit 1
fi

# 原子发布：先同步到临时目录，再一次性 mv 切换
TARGET_PARENT="$(dirname "${TARGET_DIR}")"
TARGET_NAME="$(basename "${TARGET_DIR}")"
TMP_DIR="${TARGET_PARENT}/${TARGET_NAME}.__deploying__"
BACKUP_DIR="${TARGET_PARENT}/${TARGET_NAME}.__backup__"

mkdir -p "${TARGET_PARENT}"
rm -rf "${TMP_DIR}"
mkdir -p "${TMP_DIR}"

if command -v rsync >/dev/null 2>&1; then
  rsync -av --delete "${DIST_DIR}/" "${TMP_DIR}/"
else
  echo "[deploy] rsync 不存在，使用 cp fallback" >&2
  cp -a "${DIST_DIR}/." "${TMP_DIR}/"
fi

# 原子切换（同一文件系统内 mv 是原子的）
rm -rf "${BACKUP_DIR}"
if [[ -d "${TARGET_DIR}" ]]; then
  mv "${TARGET_DIR}" "${BACKUP_DIR}"
fi
mv "${TMP_DIR}" "${TARGET_DIR}"
rm -rf "${BACKUP_DIR}" || true

echo "[deploy] 完成：已原子切换至 ${TARGET_DIR}"

# 提示：若线上仍出现 “Failed to load module script (MIME text/html)”：
# - 需要 Nginx 对 index.html 设置 no-cache；对 /assets/* 设置 immutable；
# - 且 /assets/* 不要回退到 index.html（try_files $uri =404）。















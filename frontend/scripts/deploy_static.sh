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

echo "[deploy] 发布静态资源：将 ${DIST_DIR} 同步到 ${TARGET_DIR}"

# 简单保护，防止误删根目录
if [[ "${TARGET_DIR}" == "/" ]]; then
  echo "[deploy] 目标目录异常（/），终止部署" >&2
  exit 1
fi

# 发布策略说明：
# - /assets/* 是带 hash 的不可变资源（Cache-Control: immutable），浏览器会长期缓存。
# - 若发布时删除旧的 /assets/*，用户开着旧页面在“切换栏目”（动态 import）时会 404 并白屏：
#   Failed to fetch dynamically imported module /assets/XXX.js
# - 因此这里对 /assets 采用“只增不删”（不 --delete），并在最后原子替换 index.html，
#   从而兼容“旧页面仍在运行”的情况。
#
# 代价：/assets 会逐渐累积，建议后续加按 mtime 的清理策略（保留近 N 天）。
#
# 先同步到临时目录，保证本次构建产物完整；再同步到目标目录（assets 不删），最后原子替换 index.html。
TARGET_PARENT="$(dirname "${TARGET_DIR}")"
TARGET_NAME="$(basename "${TARGET_DIR}")"
TMP_DIR="${TARGET_PARENT}/${TARGET_NAME}.__deploying__"

mkdir -p "${TARGET_PARENT}"
rm -rf "${TMP_DIR}"
mkdir -p "${TMP_DIR}"

if command -v rsync >/dev/null 2>&1; then
  rsync -av --delete "${DIST_DIR}/" "${TMP_DIR}/"
else
  echo "[deploy] rsync 不存在，使用 cp fallback" >&2
  cp -a "${DIST_DIR}/." "${TMP_DIR}/"
fi

# 确保目标目录存在
mkdir -p "${TARGET_DIR}"

if command -v rsync >/dev/null 2>&1; then
  # 1) assets：只增不删，避免旧页面动态 import 404
  if [[ -d "${TMP_DIR}/assets" ]]; then
    mkdir -p "${TARGET_DIR}/assets"
    rsync -av "${TMP_DIR}/assets/" "${TARGET_DIR}/assets/"
  fi

  # 2) 其他静态文件（除根目录 index.html 外可直接覆盖）
  # 注意：exclude 必须只排除根 index.html；否则会把 SPA 深链接兜底目录里的
  # `costing/**/index.html` 也排除，导致线上访问 `/costing/.../` 仍 403。
  rsync -av --exclude "assets/**" --exclude "/index.html" "${TMP_DIR}/" "${TARGET_DIR}/"
else
  echo "[deploy] rsync 不存在，使用 cp fallback（不删除旧 assets）" >&2
  if [[ -d "${TMP_DIR}/assets" ]]; then
    mkdir -p "${TARGET_DIR}/assets"
    cp -a "${TMP_DIR}/assets/." "${TARGET_DIR}/assets/"
  fi
  # root files
  shopt -s dotglob nullglob
  for f in "${TMP_DIR}/"*; do
    base="$(basename "${f}")"
    if [[ "${base}" == "assets" || "${base}" == "index.html" ]]; then
      continue
    fi
    cp -a "${f}" "${TARGET_DIR}/"
  done
  shopt -u dotglob nullglob
fi

# 3) index.html：最后原子替换，保证新 index 引用的 assets 已就绪
if [[ -f "${TMP_DIR}/index.html" ]]; then
  cp -a "${TMP_DIR}/index.html" "${TARGET_DIR}/index.html.__new__"
  mv "${TARGET_DIR}/index.html.__new__" "${TARGET_DIR}/index.html"
fi

rm -rf "${TMP_DIR}" || true

echo "[deploy] 完成：已原子切换至 ${TARGET_DIR}"

# 提示：若线上仍出现 “Failed to load module script (MIME text/html)”：
# - 需要 Nginx 对 index.html 设置 no-cache；对 /assets/* 设置 immutable；
# - 且 /assets/* 不要回退到 index.html（try_files $uri =404）。















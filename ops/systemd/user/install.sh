#!/usr/bin/env bash
# install.sh — 把本目录下的 systemd --user unit symlink 到 ~/.config/systemd/user/
#
# 设计原则:
#   - git 是 single source of truth: 编辑 unit = git diff = 可 review = 可恢复
#   - SERVICE: 只 link，不自动 restart（避免无谓中断生产 API/同步）
#   - TIMER:   enable --now（幂等，无害）
#   - SECRET:  *.secret.conf 文件不在 git 内，install.sh 不动它们
#
# 用法:
#   ops/systemd/user/install.sh         # 安装 + enable timers (不重启 service)
#   ops/systemd/user/install.sh --check # 仅检查链接 + secret 是否就位，不改任何东西
#   ops/systemd/user/install.sh --restart-services  # 危险：重启所有 service（API/sync 会短暂中断）
set -euo pipefail

SRC_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
DEST_DIR="$HOME/.config/systemd/user"
WANTS_DIR="$DEST_DIR/timers.target.wants"

# Service files (linked to ~/.config; NOT auto-restarted to avoid downtime)
SERVICES=(
  ai-costing-snapshot-sweep.service
  ai-costing-data-quality.service
  ai-costing-nightly-refresh.service
  costing-workspace-health.service
  costing-audit-summary.service
  jackyun-shipment-sync.service
  jackyun-refund-sync.service
  planner-costing.service
)

# Timer files (linked + enable --now, harmless to re-run)
TIMERS=(
  ai-costing-snapshot-sweep.timer
  ai-costing-data-quality.timer
  ai-costing-nightly-refresh.timer
  costing-workspace-health.timer
  costing-audit-summary.timer
  jackyun-shipment-sync.timer
  jackyun-refund-sync.timer
)

# Secret drop-in files that MUST exist in destination but NOT in git.
# install.sh checks they're present (--check mode) but never overwrites.
REQUIRED_SECRETS=(
  "planner-costing.service.d/dingtalk.conf"
  "planner-costing.service.d/llm_key.conf"
)

mkdir -p "$DEST_DIR" "$DEST_DIR/planner-costing.service.d"

# -------- --check --------
if [ "${1:-}" = "--check" ]; then
  status=0
  echo "→ checking unit symlinks (should point into git repo)"
  for u in "${SERVICES[@]}" "${TIMERS[@]}"; do
    target="$DEST_DIR/$u"
    if [ ! -L "$target" ] && [ ! -f "$target" ]; then
      echo "  MISSING: $target"; status=1
    elif [ -L "$target" ] && [ ! -e "$target" ]; then
      echo "  BROKEN : $target -> $(readlink "$target")"; status=1
    elif [ -L "$target" ]; then
      lk="$(readlink "$target")"
      case "$lk" in
        "$SRC_DIR"/*) echo "  OK     : $u" ;;
        *) echo "  WARN   : $u -> $lk (not in this repo)"; status=1 ;;
      esac
    else
      echo "  ORPHAN : $u (regular file, not symlinked to git — call install.sh to fix)"; status=1
    fi
  done

  echo "→ checking dropin / sub-files"
  for d in "$SRC_DIR"/*.service.d/*.conf; do
    [ -e "$d" ] || continue
    name="${d#$SRC_DIR/}"
    target="$DEST_DIR/$name"
    if [ ! -L "$target" ] && [ ! -f "$target" ]; then
      echo "  MISSING: $target"; status=1
    elif [ -L "$target" ] && [ ! -e "$target" ]; then
      echo "  BROKEN : $target -> $(readlink "$target")"; status=1
    else
      echo "  OK     : $name"
    fi
  done

  echo "→ checking required secrets (NOT in git, must be deployed manually)"
  for s in "${REQUIRED_SECRETS[@]}"; do
    if [ -f "$DEST_DIR/$s" ]; then
      echo "  OK     : $s"
    else
      echo "  MISSING: $DEST_DIR/$s — restore from secure backup before next service restart!"
      status=1
    fi
  done

  echo "→ checking dangling timers.target.wants symlinks"
  for u in "${TIMERS[@]}"; do
    link="$WANTS_DIR/$u"
    if [ -L "$link" ] && [ ! -e "$link" ]; then
      echo "  BROKEN WANTS: $link -> $(readlink "$link")"; status=1
    fi
  done

  exit $status
fi

# -------- normal install --------
echo "→ symlinking $((${#SERVICES[@]} + ${#TIMERS[@]})) units from $SRC_DIR to $DEST_DIR"
for u in "${SERVICES[@]}" "${TIMERS[@]}"; do
  src="$SRC_DIR/$u"
  dst="$DEST_DIR/$u"
  if [ -L "$dst" ] && [ "$(readlink "$dst")" = "$src" ]; then
    : # already correct
  else
    rm -f "$dst"
    ln -s "$src" "$dst"
    echo "  + $u"
  fi
done

echo "→ symlinking dropin .conf files (excluding secrets)"
for d in "$SRC_DIR"/*.service.d/*.conf; do
  [ -e "$d" ] || continue
  rel="${d#$SRC_DIR/}"
  dst="$DEST_DIR/$rel"
  mkdir -p "$(dirname "$dst")"
  if [ -L "$dst" ] && [ "$(readlink "$dst")" = "$d" ]; then
    : # already correct
  else
    rm -f "$dst"
    ln -s "$d" "$dst"
    echo "  + $rel"
  fi
done

echo "→ checking required secrets are present"
missing_secret=0
for s in "${REQUIRED_SECRETS[@]}"; do
  if [ ! -f "$DEST_DIR/$s" ]; then
    echo "  ❗ MISSING: $DEST_DIR/$s"
    missing_secret=1
  fi
done
if [ "$missing_secret" -ne 0 ]; then
  echo "  → secrets are not in git (intentional). Restore from secure backup."
fi

echo "→ cleaning broken wants symlinks"
for u in "${TIMERS[@]}"; do
  link="$WANTS_DIR/$u"
  if [ -L "$link" ] && [ ! -e "$link" ]; then
    rm -f "$link"
    echo "  - $link (was broken)"
  fi
done

echo "→ daemon-reload"
systemctl --user daemon-reload

echo "→ enabling timers (--now is harmless to re-run)"
systemctl --user enable --now "${TIMERS[@]}"

echo "→ enabling services (NOT restarting — use --restart-services if you really want to)"
systemctl --user enable "${SERVICES[@]}" 2>&1 | grep -v 'already enabled' || true

if [ "${1:-}" = "--restart-services" ]; then
  echo "→ ⚠ restarting services (production traffic will see brief interruption)"
  systemctl --user restart "${SERVICES[@]}"
fi

echo
echo "→ done. Timer status:"
systemctl --user list-timers "${TIMERS[@]}" --no-pager

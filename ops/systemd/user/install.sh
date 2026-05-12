#!/usr/bin/env bash
# install.sh — 把本目录下的 systemd --user unit 文件 symlink 到 ~/.config/systemd/user/
# 用 symlink (不是 cp) 是为了：git 是单一真相源，改 unit 直接改这里、git push、
# 别人 pull 后 install.sh 就生效；同时如果 IDE/sync 又把 ~/.config 里的文件删了，
# install.sh 一行就能恢复。
#
# 用法:
#   ops/systemd/user/install.sh         # 安装 + enable + daemon-reload
#   ops/systemd/user/install.sh --check # 仅检查链接是否 OK，不改任何东西
set -euo pipefail

SRC_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
DEST_DIR="$HOME/.config/systemd/user"
WANTS_DIR="$DEST_DIR/timers.target.wants"

UNITS=(
  ai-costing-snapshot-sweep.service
  ai-costing-snapshot-sweep.timer
  ai-costing-data-quality.service
  ai-costing-data-quality.timer
  costing-workspace-health.service
  costing-workspace-health.timer
)

mkdir -p "$DEST_DIR"

if [ "${1:-}" = "--check" ]; then
  status=0
  for u in "${UNITS[@]}"; do
    target="$DEST_DIR/$u"
    if [ ! -L "$target" ] && [ ! -f "$target" ]; then
      echo "MISSING: $target"; status=1
    elif [ -L "$target" ] && [ ! -e "$target" ]; then
      echo "BROKEN: $target -> $(readlink "$target")"; status=1
    else
      printf "OK     : %s -> %s\n" "$target" "$(readlink "$target" 2>/dev/null || echo '(regular file)')"
    fi
  done
  for u in ai-costing-snapshot-sweep.timer ai-costing-data-quality.timer; do
    link="$WANTS_DIR/$u"
    if [ -L "$link" ] && [ ! -e "$link" ]; then
      echo "BROKEN WANTS: $link -> $(readlink "$link")"; status=1
    fi
  done
  exit $status
fi

echo "→ symlinking units from $SRC_DIR to $DEST_DIR"
for u in "${UNITS[@]}"; do
  src="$SRC_DIR/$u"
  dst="$DEST_DIR/$u"
  rm -f "$dst"
  ln -s "$src" "$dst"
  echo "  + $u"
done

echo "→ cleaning broken wants symlinks (defensive — daemon-reload otherwise complains)"
for u in ai-costing-snapshot-sweep.timer ai-costing-data-quality.timer; do
  link="$WANTS_DIR/$u"
  if [ -L "$link" ] && [ ! -e "$link" ]; then
    rm -f "$link"
    echo "  - $link (was broken)"
  fi
done

echo "→ daemon-reload"
systemctl --user daemon-reload

echo "→ enable + start timers"
systemctl --user enable --now \
  ai-costing-snapshot-sweep.timer \
  ai-costing-data-quality.timer \
  costing-workspace-health.timer

echo "→ done. timers status:"
systemctl --user list-timers \
  ai-costing-snapshot-sweep.timer \
  ai-costing-data-quality.timer \
  costing-workspace-health.timer \
  --no-pager

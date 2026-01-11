from __future__ import annotations

import argparse
import time
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="清理发货导入预览缓存文件（backend/logs/shipment_previews）")
    parser.add_argument(
        "--dir",
        default="/home/admin/ai-costing-system/backend/logs/shipment_previews",
        help="预览缓存目录",
    )
    parser.add_argument("--older-than-days", type=int, default=7, help="删除多少天以前的文件（默认7天）")
    parser.add_argument("--dry-run", action="store_true", help="只打印将删除的文件，不实际删除（默认推荐先开）")
    parser.add_argument("--delete-all", action="store_true", help="忽略天数阈值，删除目录下所有xlsx")
    args = parser.parse_args()

    d = Path(args.dir)
    if not d.exists():
        print(f"[skip] dir not found: {d}")
        return 0

    now = time.time()
    threshold = now - max(args.older_than_days, 0) * 86400

    files = sorted([p for p in d.glob("*.xlsx") if p.is_file()], key=lambda p: p.stat().st_mtime)
    if not files:
        print(f"[ok] no preview files under: {d}")
        return 0

    to_delete = []
    for p in files:
        mtime = p.stat().st_mtime
        if args.delete_all or mtime < threshold:
            to_delete.append(p)

    if not to_delete:
        print(f"[ok] nothing to delete (older_than_days={args.older_than_days}) under: {d}")
        return 0

    total_bytes = sum(p.stat().st_size for p in to_delete)
    print(f"[plan] delete {len(to_delete)} files, total={total_bytes/1024/1024:.2f}MB, dir={d}")
    for p in to_delete[:20]:
        print(" -", p.name)
    if len(to_delete) > 20:
        print(f" ... and {len(to_delete) - 20} more")

    if args.dry_run:
        print("[dry-run] no files deleted")
        return 0

    deleted = 0
    for p in to_delete:
        try:
            p.unlink()
            deleted += 1
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] failed delete {p}: {exc}")

    print(f"[ok] deleted {deleted}/{len(to_delete)} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())



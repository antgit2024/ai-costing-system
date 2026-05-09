"""一次性回填 / nightly 定时任务入口：批量重算 SKU "数据质量"标签。

用法：
  # 全部历史发货，落库（默认只看带真实订单号的发货行）
  PYTHONPATH=. .venv/bin/python scripts/backfill_data_quality_status.py

  # 仅看效果，不落库（dry-run）
  PYTHONPATH=. .venv/bin/python scripts/backfill_data_quality_status.py --dry-run

  # 仅最近 30 天发货
  PYTHONPATH=. .venv/bin/python scripts/backfill_data_quality_status.py --lookback 30

  # 把 Excel 历史也算进去（一般不要，会大量误报）
  PYTHONPATH=. .venv/bin/python scripts/backfill_data_quality_status.py --include-excel
"""

from __future__ import annotations

import argparse
import json
import sys

sys.path.insert(0, ".")

from src.database import SessionLocal
from src.planner.services import data_quality_service as dq


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--lookback",
        type=int,
        default=0,
        help="回看天数（0 = 全部历史，默认 0；nightly 任务推荐 90）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只算不落库",
    )
    parser.add_argument(
        "--include-excel",
        action="store_true",
        help=(
            "默认只看带真实 erp_order_no/platform_order_no 的发货行（吉客云同步）。"
            "加这个 flag 会把 Excel 灌的历史回测数据也算进去——容易大量误报，"
            "仅用于排查。"
        ),
    )
    parser.add_argument(
        "--clear-stale",
        action="store_true",
        help=(
            "对被打过 SPU 错配标记、本次扫描却扫不到（lookback 内没真实订单）"
            "的 SKU，也强制清掉旧标记。规则切换 / 一次性回填请打开；"
            "nightly 任务不要开。"
        ),
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        stats = dq.recompute_all(
            db,
            lookback_days=args.lookback,
            dry_run=args.dry_run,
            only_with_real_order=not args.include_excel,
            clear_stale_for_skus_without_real_data=args.clear_stale,
        )
    finally:
        db.close()

    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

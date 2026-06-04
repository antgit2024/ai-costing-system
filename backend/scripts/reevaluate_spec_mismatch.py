"""Re-evaluate every SkuMaster row currently flagged ``spec_mismatch=True``
under the new smart rules:

  - Real mismatch only if dimensions differ OR keyword conflict
  - All "字符顺序变化 / 颜色前缀差异 / token 子集" false positives are cleared

Skips rows whose operator has already explicitly resolved the mismatch
(``metadata.spec_mismatch_resolved = True``) — those decisions stand.

Usage:
    PYTHONPATH=. .venv/bin/python scripts/reevaluate_spec_mismatch.py --dry-run
    PYTHONPATH=. .venv/bin/python scripts/reevaluate_spec_mismatch.py
    PYTHONPATH=. .venv/bin/python scripts/reevaluate_spec_mismatch.py --barcode 6011013268917
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import src.compat  # noqa: F401, E402
from sqlalchemy import text  # noqa: E402

from src.database import SessionLocal, configure_engine  # noqa: E402
from src.planner import models  # noqa: E402
from src.planner.services import sku_master_service  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Preview only, don't write")
    parser.add_argument("--barcode", type=str, default=None, help="Restrict to a single SKU (debugging)")
    parser.add_argument("--limit", type=int, default=0, help="Cap rows processed (0 = all)")
    args = parser.parse_args()

    configure_engine()
    db = SessionLocal()
    try:
        q = (
            db.query(models.SkuMaster)
            .filter(
                models.SkuMaster.is_archived.is_(False),
                models.SkuMaster.metadata_json["spec_mismatch"].as_boolean() == True,  # noqa: E712
            )
            .order_by(models.SkuMaster.id.asc())
        )
        if args.barcode:
            q = q.filter(models.SkuMaster.erp_sku_barcode == args.barcode.strip())

        rows = q.all()
        total = len(rows)
        print(f"[scan] sku_master rows currently flagged spec_mismatch=True : {total}")
        if total == 0:
            return 0

        counter: Counter[str] = Counter()
        sample_cleared = []
        sample_keep = []

        processed = 0
        for sm in rows:
            res = sku_master_service.reevaluate_spec_mismatch_by_id(db, sku_master_id=str(sm.id))
            if res.get("skipped"):
                counter[f"skipped:{res.get('reason')}"] += 1
                continue
            before = bool(res.get("before"))
            after = bool(res.get("after"))
            if before and not after:
                counter["cleared"] += 1
                if len(sample_cleared) < 5:
                    sample_cleared.append((sm.erp_sku_barcode, res.get("detail")))
            elif before and after:
                counter[f"kept:{res.get('reason') or 'unknown'}"] += 1
                if len(sample_keep) < 5:
                    sample_keep.append((sm.erp_sku_barcode, res.get("reason"), res.get("detail")))
            else:
                counter["other"] += 1

            processed += 1
            if not args.dry_run and processed % 200 == 0:
                db.commit()
                print(f"[commit] {processed}/{total}")

            if args.limit and processed >= args.limit:
                break

        if args.dry_run:
            db.rollback()
        else:
            db.commit()

        print("\n[result]")
        for k, v in counter.most_common():
            print(f"  {k:>40} : {v}")
        print(f"\n  cleared = 之前误标、现在已清除的（假阳性）")
        print(f"  kept:dimension_mismatch = 真有尺寸差异（必须运营关注）")
        print(f"  kept:keyword_conflict   = 关键词冲突（疑似贴错码）")

        if sample_cleared:
            print("\n[sample] 已清除的假阳性（前 5）：")
            for sku, detail in sample_cleared:
                print(f"  {sku!r:>20}  {detail}")
        if sample_keep:
            print("\n[sample] 保留的真差异（前 5）：")
            for sku, reason, detail in sample_keep:
                print(f"  {sku!r:>20}  reason={reason}  {detail}")

        if args.dry_run:
            print("\n[dry-run] no changes written")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())

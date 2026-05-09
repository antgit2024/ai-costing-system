"""Quick dry-run probe: how many unbound SKUs can auto_bind_preview match
now that we backfilled shop_spec_code? Reports per-method counts.

Run:
  PYTHONPATH=. .venv/bin/python scripts/probe_auto_bind_after_backfill.py
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import src.compat  # noqa: F401, E402
from src.database import SessionLocal, configure_engine  # noqa: E402
from src.planner.services import sku_master_service  # noqa: E402


def main() -> int:
    configure_engine()
    db = SessionLocal()
    try:
        result = sku_master_service.auto_bind_preview(db, limit=20000, scan_limit=20000)
        items = result.get("items") or []
        method_counter: Counter[str] = Counter()
        for it in items:
            method_counter[it.get("match_method") or "unknown"] += 1

        print(f"[probe] total_unbound (sample bounded by scan_limit) ≈ {result.get('total_unbound')}")
        print(f"[probe] candidates with a model match: {result.get('candidates')}")
        print("[probe] per match_method breakdown:")
        for method, cnt in method_counter.most_common():
            print(f"        {method:>20} : {cnt}")

        print("\n[probe] first 10 shop_spec_code-driven matches:")
        shown = 0
        for it in items:
            if it.get("match_method") == "shop_spec_code":
                print(
                    f"  sku={it.get('erp_sku_barcode')!r:>20} "
                    f"shop={it.get('shop_spec_code')!r:>16} "
                    f"-> model={it.get('model_code')!r} ({it.get('model_name')})"
                    f" variant_hint={it.get('variant_code_hint')!r}"
                )
                shown += 1
                if shown >= 10:
                    break
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())

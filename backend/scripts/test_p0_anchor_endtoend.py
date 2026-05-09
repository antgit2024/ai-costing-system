"""End-to-end P0 anchor test:

1. Force sku_master.metadata.shop_spec_code = 'KB8-001' for two test SKUs
2. Force the latest active shipment_lines row for each SKU to the same value
   (so the 发货管理 / 发货台账 UI shows the new merchant code)
3. Run auto_bind_preview restricted to these two SKUs — verify match_method
   is 'shop_spec_code' and target is KB8 / KB8-001
4. Run auto_bind_execute on those preview rows — actually bind
5. Re-query bindings to confirm
"""
from __future__ import annotations
import sys
from pathlib import Path
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
import src.compat  # noqa: F401, E402
from datetime import datetime, timezone  # noqa: E402

from sqlalchemy import text  # noqa: E402
from sqlalchemy.orm.attributes import flag_modified  # noqa: E402

from src.database import SessionLocal, configure_engine  # noqa: E402
from src.planner import models  # noqa: E402
from src.planner.services import sku_master_service  # noqa: E402

BARCODES = ["6235739486141", "6232909415886"]
NEW_SHOP_SPEC = "KB8-001"


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def main() -> int:
    configure_engine()
    db = SessionLocal()
    try:
        print("=" * 60)
        print(f"STEP 1/5: force sku_master.shop_spec_code = {NEW_SHOP_SPEC}")
        print("=" * 60)
        sm_rows = db.query(models.SkuMaster).filter(
            models.SkuMaster.erp_sku_barcode.in_(BARCODES)
        ).all()
        for sm in sm_rows:
            meta = dict(sm.metadata_json or {})
            old = meta.get("shop_spec_code")
            meta["shop_spec_code"] = NEW_SHOP_SPEC
            meta["shop_spec_code_source"] = "manual_override_test"
            meta["shop_spec_code_seen_at"] = _now_iso()
            sm.metadata_json = meta
            flag_modified(sm, "metadata_json")
            print(f"  {sm.erp_sku_barcode}: {old!r} -> {NEW_SHOP_SPEC!r}")
        db.commit()

        print("\n" + "=" * 60)
        print("STEP 2/5: force latest shipment_line.shop_spec_code (UI display)")
        print("=" * 60)
        for bc in BARCODES:
            line = (
                db.query(models.ShipmentLine)
                .filter(
                    models.ShipmentLine.sku_code == bc,
                    models.ShipmentLine.is_archived.is_(False),
                )
                .order_by(models.ShipmentLine.created_at.desc())
                .first()
            )
            if not line:
                print(f"  {bc}: no shipment_line found, skipped")
                continue
            meta = dict(line.metadata_json or {})
            old = meta.get("shop_spec_code")
            meta["shop_spec_code"] = NEW_SHOP_SPEC
            line.metadata_json = meta
            flag_modified(line, "metadata_json")
            print(f"  {bc}/line={line.id}: {old!r} -> {NEW_SHOP_SPEC!r}")
        db.commit()

        print("\n" + "=" * 60)
        print("STEP 3/5: auto_bind_preview restricted to 2 test SKUs")
        print("=" * 60)
        preview = sku_master_service.auto_bind_preview(
            db, limit=20, scan_limit=20, restrict_to_sku_codes=BARCODES
        )
        items = preview.get("items") or []
        print(f"  total_unbound (in restrict)={preview.get('total_unbound')}")
        print(f"  candidates                 ={preview.get('candidates')}")
        for it in items:
            print(f"  -> sku={it.get('erp_sku_barcode')!r}")
            print(f"     shop_spec_code  = {it.get('shop_spec_code')!r}")
            print(f"     model_code_hint = {it.get('model_code_hint')!r}")
            print(f"     variant_hint    = {it.get('variant_code_hint')!r}")
            print(f"     match_method    = {it.get('match_method')!r}")
            print(f"     -> model        = {it.get('model_code')} / {it.get('model_name')}")
            print(f"     -> version      = {it.get('version_label')}")

        if not items or any(it.get("match_method") != "shop_spec_code" for it in items):
            print("\n  [WARN] expected match_method='shop_spec_code' on all rows")
            print("  Aborting before execute to keep DB unchanged for diagnosis.")
            return 1

        print("\n" + "=" * 60)
        print("STEP 4/5: auto_bind_execute on the preview rows")
        print("=" * 60)
        sm_ids = [str(it.get("sku_master_id")) for it in items if it.get("sku_master_id")]
        # NOTE: auto_bind_execute does NOT take restrict_to_sku_codes — it
        # internally re-runs preview over the full unbound set, then filters
        # by sku_master_ids. To avoid scanning everything, we'll just look
        # at the result's diff for our 2 SKUs.
        exec_result = sku_master_service.auto_bind_execute(
            db,
            limit=2000,
            scan_limit=20000,
            requested_by="p0_anchor_endtoend_test",
            sku_master_ids=sm_ids,
        )
        # auto_bind_execute return shape varies; just dump it
        print(f"  exec_result keys: {list(exec_result.keys())}")
        for k, v in exec_result.items():
            if isinstance(v, (list, dict)):
                print(f"  {k}: <{type(v).__name__} len={len(v)}>")
            else:
                print(f"  {k}: {v}")

        print("\n" + "=" * 60)
        print("STEP 5/5: verify bindings persisted")
        print("=" * 60)
        for bc in BARCODES:
            row = db.execute(text(
                "SELECT pm.model_code, pm.model_name, pmv.version_label, "
                "sm.metadata->>'bound_variant_code' AS bvc "
                "FROM sku_model_version_mapping m "
                "JOIN product_model_versions pmv ON pmv.id = m.model_version_id "
                "JOIN product_models pm ON pm.id = pmv.model_id "
                "JOIN sku_master sm ON sm.erp_sku_barcode = m.sku_code "
                "WHERE m.sku_code = :bc AND m.is_active = TRUE AND m.is_archived = FALSE"
            ), {"bc": bc}).first()
            if row:
                label = f"{row.model_code} / {row.model_name} (variant={row.bvc})"
            else:
                label = "(no active binding)"
            print(f"  {bc}: BOUND -> {label}")

        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())

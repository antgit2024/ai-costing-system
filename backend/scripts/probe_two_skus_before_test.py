"""Inspect two SKUs before forcing shop_spec_code = 'KB8-001'."""
from __future__ import annotations
import sys
from pathlib import Path
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
import src.compat  # noqa: F401, E402
from sqlalchemy import text  # noqa: E402
from src.database import SessionLocal, configure_engine  # noqa: E402

BARCODES = ["6235739486141", "6232909415886"]

configure_engine()
db = SessionLocal()
try:
    for bc in BARCODES:
        print(f"\n=== {bc} ===")
        sm = db.execute(text(
            "SELECT id, erp_sku_barcode, channel, spec_text, "
            "metadata->>'shop_spec_code' AS shop_spec_code, "
            "metadata->>'bound_variant_code' AS bound_variant_code, "
            "metadata->>'governance_status' AS governance_status "
            "FROM sku_master WHERE erp_sku_barcode = :bc"
        ), {"bc": bc}).first()
        if not sm:
            print("  [no sku_master row]")
            continue
        sm_id, _, channel, spec_text, shop, bvc, gov = sm
        print(f"  sku_master.id          = {sm_id}")
        print(f"  channel                = {channel!r}")
        print(f"  spec_text              = {spec_text!r}")
        print(f"  metadata.shop_spec_code= {shop!r}")
        print(f"  metadata.bound_variant_code = {bvc!r}")
        print(f"  metadata.governance_status  = {gov!r}")

        binding = db.execute(text(
            "SELECT m.id, m.model_version_id, pmv.version_label, pm.model_code, pm.model_name "
            "FROM sku_model_version_mapping m "
            "JOIN product_model_versions pmv ON pmv.id = m.model_version_id "
            "JOIN product_models pm ON pm.id = pmv.model_id "
            "WHERE m.sku_code = :bc AND m.is_active = TRUE AND m.is_archived = FALSE"
        ), {"bc": bc}).first()
        if binding:
            print(f"  CURRENT BINDING        = {binding.model_code} / {binding.model_name} ({binding.version_label})")
        else:
            print(f"  CURRENT BINDING        = (none, will be scanned by auto_bind_preview)")

        ship_count = db.execute(text(
            "SELECT count(*) FROM shipment_lines WHERE sku_code = :bc AND is_archived = FALSE"
        ), {"bc": bc}).scalar()
        print(f"  shipment_lines count   = {ship_count}")

    print("\n=== KB8 model status ===")
    kb8 = db.execute(text(
        "SELECT pm.id, pm.model_code, pm.model_name, pm.is_archived, "
        "pmv.id AS version_id, pmv.version_label, pmv.version_status, pmv.version_kind "
        "FROM product_models pm "
        "LEFT JOIN product_model_versions pmv ON pmv.model_id = pm.id "
        "WHERE pm.model_code = 'KB8' "
        "ORDER BY pmv.created_at DESC NULLS LAST LIMIT 5"
    )).all()
    for row in kb8:
        print(f"  model={row.model_code} {row.model_name!r} archived={row.is_archived} "
              f"version={row.version_label} status={row.version_status} kind={row.version_kind}")

    print("\n=== KB8 variants (by metadata.variant_code) ===")
    var = db.execute(text(
        "SELECT pmlv.id, pmlv.metadata->>'variant_code' AS variant_code, "
        "pmlv.metadata->>'display_name' AS display_name, "
        "pmlv.priority, pmlv.enabled, pmv.version_label "
        "FROM product_model_line_variants pmlv "
        "JOIN product_model_versions pmv ON pmv.id = pmlv.version_id "
        "JOIN product_models pm ON pm.id = pmv.model_id "
        "WHERE pm.model_code = 'KB8' AND pmlv.is_archived = FALSE "
        "ORDER BY pmlv.priority ASC LIMIT 12"
    )).all()
    for v in var:
        print(f"  variant_code={v.variant_code!r:>12} display={v.display_name!r:>20} "
              f"version={v.version_label} prio={v.priority} enabled={v.enabled}")
finally:
    db.close()

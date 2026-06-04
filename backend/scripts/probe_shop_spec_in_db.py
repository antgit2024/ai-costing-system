"""Sanity check: are the backfilled shop_spec_code values actually visible in DB?"""
from __future__ import annotations
import sys
from pathlib import Path
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
import src.compat  # noqa: F401, E402
from sqlalchemy import func, text  # noqa: E402
from src.database import SessionLocal, configure_engine  # noqa: E402
from src.planner import models  # noqa: E402

configure_engine()
db = SessionLocal()
try:
    r1 = db.execute(text(
        "SELECT count(*) FROM sku_master "
        "WHERE metadata->>'shop_spec_code' IS NOT NULL "
        "AND metadata->>'shop_spec_code' != ''"
    )).scalar()
    r2 = db.execute(text(
        "SELECT count(*) FROM sku_master "
        "WHERE metadata->>'shop_spec_code_source' = 'backfill_from_shipment'"
    )).scalar()
    print(f"sku_master rows with non-empty shop_spec_code: {r1}")
    print(f"  of which backfilled by script:               {r2}")

    # Sample a few that look like structured codes (KB8-001 style)
    rows = db.execute(text(
        "SELECT erp_sku_barcode, metadata->>'shop_spec_code' AS shop "
        "FROM sku_master "
        "WHERE metadata->>'shop_spec_code' ~ '^[A-Za-z0-9]{3}-[A-Za-z0-9]{2,8}$' "
        "LIMIT 10"
    )).all()
    print("\nstructured shop_spec_code samples (XXX-XXX):")
    for sku, shop in rows:
        print(f"  {sku!r:>20} -> {shop!r}")

    # Cross-check unbound + structured
    rows2 = db.execute(text(
        "SELECT count(*) FROM sku_master sm "
        "WHERE metadata->>'shop_spec_code' ~ '^[A-Za-z0-9]{3}-[A-Za-z0-9]{2,8}$' "
        "AND NOT EXISTS ("
        "  SELECT 1 FROM sku_model_version_mapping m "
        "  WHERE m.sku_code = sm.erp_sku_barcode "
        "  AND m.is_active = TRUE AND m.is_archived = FALSE"
        ")"
    )).scalar()
    print(f"\nUNBOUND + structured shop_spec_code (should drive auto-match): {rows2}")
finally:
    db.close()

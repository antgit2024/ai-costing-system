"""Reset 6235739486141 binding so we can re-test the fixed auto_bind_execute."""
from __future__ import annotations
import sys
from pathlib import Path
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
import src.compat  # noqa: F401, E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.orm.attributes import flag_modified  # noqa: E402
from src.database import SessionLocal, configure_engine  # noqa: E402
from src.planner import models  # noqa: E402

configure_engine()
db = SessionLocal()
try:
    for bc in ["6235739486141", "6232909415886"]:
        # Soft delete active mapping
        n = db.execute(text(
            "UPDATE sku_model_version_mapping "
            "SET is_active=FALSE, is_archived=TRUE "
            "WHERE sku_code=:bc AND is_active=TRUE AND is_archived=FALSE"
        ), {"bc": bc}).rowcount
        # Clear bound_variant_code on sku_master
        sm = db.query(models.SkuMaster).filter(models.SkuMaster.erp_sku_barcode == bc).first()
        if sm:
            meta = dict(sm.metadata_json or {})
            popped = meta.pop("bound_variant_code", None)
            sm.metadata_json = meta
            flag_modified(sm, "metadata_json")
            print(f"  {bc}: deactivated {n} mapping(s); cleared bound_variant_code={popped!r}")
    db.commit()
    print("[done] reset complete")
finally:
    db.close()

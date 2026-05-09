"""Distribution of backfilled shop_spec_code by shape — to understand
how many will actually drive auto-match TODAY vs how many need user
edits in 吉客云 first."""
from __future__ import annotations
import re, sys
from collections import Counter
from pathlib import Path
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
import src.compat  # noqa: F401, E402
from sqlalchemy import text  # noqa: E402
from src.database import SessionLocal, configure_engine  # noqa: E402

configure_engine()
db = SessionLocal()
try:
    rows = db.execute(text(
        "SELECT metadata->>'shop_spec_code' AS shop FROM sku_master "
        "WHERE metadata->>'shop_spec_code' IS NOT NULL "
        "AND metadata->>'shop_spec_code' != ''"
    )).all()
    pat_xxx_xxx = re.compile(r"^[A-Z0-9]{3}-[A-Z0-9]{2,8}$")
    pat_3char = re.compile(r"^[A-Z0-9]{3}$")
    pat_pure_digits = re.compile(r"^\d+$")
    pat_pm = re.compile(r"^PM[A-Z0-9_-]+$")
    buckets = Counter()
    samples_by_bucket: dict[str, list[str]] = {}
    for (shop,) in rows:
        s = (shop or "").strip().upper()
        if pat_xxx_xxx.match(s):
            b = "XXX-XXX (auto-match P0)"
        elif pat_3char.match(s):
            b = "XXX (3-char model code)"
        elif pat_pm.match(s):
            b = "PM-prefixed legacy"
        elif pat_pure_digits.match(s):
            b = "pure digits (platform ID)"
        else:
            b = "other (probably needs cleanup)"
        buckets[b] += 1
        samples_by_bucket.setdefault(b, []).append(s)

    print(f"Total backfilled rows: {sum(buckets.values())}\n")
    for b, c in buckets.most_common():
        pct = 100.0 * c / sum(buckets.values())
        print(f"  {b:<35} : {c:>6}  ({pct:5.1f}%)")
        for sample in samples_by_bucket[b][:3]:
            print(f"        sample: {sample}")
finally:
    db.close()

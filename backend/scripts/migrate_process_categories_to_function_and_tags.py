"""
One-off migration:
- Normalize process_category taxonomy items:
  - Strip suffix "(画艺)/(布艺)" from name (also supports "（画艺）/（布艺）")
  - Set scopes_json to ["*"] for all process_category items
  - (Optional) keep old items but mark archived if name changes and new name exists
- Normalize processes.category similarly
- Move the suffix label (画艺/布艺) into processes.metadata_json["process_tags"] (append, de-dupe)

Run:
  PYTHONPATH=. backend/.venv/bin/python3.12 backend/scripts/migrate_process_categories_to_function_and_tags.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Ensure repo root is on sys.path so `src.*` imports work when running as a script
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.src.config import settings  # type: ignore
from backend.src.planner import models  # type: ignore


SUFFIX_RE = re.compile(r"\s*[\(（]\s*(画艺|布艺)\s*[\)）]\s*$")


def strip_suffix(name: str) -> tuple[str, str | None]:
    s = (name or "").strip()
    m = SUFFIX_RE.search(s)
    if not m:
        return s, None
    tag = m.group(1)
    base = SUFFIX_RE.sub("", s).strip()
    return base, tag


def main() -> None:
    engine = create_engine(settings.database_url)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        # 1) Taxonomy: process_category scopes -> ["*"], strip suffixes
        items = (
            db.query(models.TaxonomyItem)
            .filter(models.TaxonomyItem.domain == "process_category", models.TaxonomyItem.is_archived.is_(False))
            .all()
        )
        name_to_item: dict[str, models.TaxonomyItem] = {it.name: it for it in items}
        category_to_scopes: dict[str, list[str]] = {}

        updated_items = 0
        archived_items = 0
        created_items = 0
        for it in items:
            # capture non-universal scopes as tags to be migrated to processes
            scopes = it.scopes_json if isinstance(it.scopes_json, list) else []
            scopes = [str(x).strip() for x in scopes if str(x).strip()]
            non_universal = [s for s in scopes if s != "*"]
            if non_universal:
                category_to_scopes[it.name] = non_universal

            # force universal scope for categories (category is functional, not line-specific)
            it.scopes_json = ["*"]

            base, _tag = strip_suffix(it.name)
            if base and base != it.name:
                # If a clean-name item already exists, archive the old one; otherwise rename in-place.
                if base in name_to_item and name_to_item[base].id != it.id:
                    it.is_archived = True
                    archived_items += 1
                else:
                    it.name = base
                    name_to_item[base] = it
                    updated_items += 1

        # Ensure we have at least one "分切" etc? (no-op; user will manage)

        # 2) Processes: normalize category and move suffix tag -> metadata_json.process_tags
        procs = db.query(models.Process).filter(models.Process.is_archived.is_(False)).all()
        updated_procs = 0
        tagged_procs = 0
        for p in procs:
            cat = (p.category or "").strip()
            if not cat:
                continue
            base, tag = strip_suffix(cat)
            if base != cat:
                p.category = base or None
                updated_procs += 1
            tags_to_add: list[str] = []
            if tag:
                tags_to_add.append(tag)
            # migrate category scopes -> process tags
            tags_to_add.extend(category_to_scopes.get(base or cat, []))
            if tags_to_add:
                meta = dict(p.metadata_json or {})
                tags = meta.get("process_tags")
                if not isinstance(tags, list):
                    tags = []
                tags = [str(x).strip() for x in tags if str(x).strip()]
                before = set(tags)
                for t in tags_to_add:
                    if t and t not in before:
                        tags.append(t)
                        before.add(t)
                        tagged_procs += 1
                meta["process_tags"] = tags
                p.metadata_json = meta

        db.commit()
        print(
            f"[ok] taxonomy_items updated={updated_items} archived={archived_items} created={created_items}; "
            f"processes category_updated={updated_procs} tag_appended={tagged_procs}"
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()



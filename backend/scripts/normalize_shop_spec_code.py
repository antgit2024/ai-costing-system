"""一次性回填：清理历史 shop_spec_code 中"款号前缀+模型变体码"的脏拼装。

背景
====
吉客云端运营在网店"商家编码"字段常把 ``<商品款号><模型变体码>`` 拼起来录入：
    Q26041801KB8-001
    J26042802KB8-001
我们 mapper 历史上原样落库，导致：
  - 自动绑定的 P0 锚点 ``_extract_model_code_from_shop_spec`` 抓不到 KB8
  - 前端"商家编码"列显示成 ``Q26041801KB8-001``，运营要扫一眼也累

2026-05-12 起 mapper 已经在新数据落库时做归一化，这脚本扫一次历史，把存量
``shipment_lines.metadata.shop_spec_code`` 和 ``sku_master.metadata.shop_spec_code``
都做一次归一化，原始拼装保留到 ``shop_spec_code_raw`` 给运营审计。

安全规则（与 mapper 同源 ``_normalize_shop_spec_code``）：
  - 只剥末尾段是真实存在的 ``product_models.model_code`` 的前缀
  - ``Q26041801KB8-001``  → ``KB8-001``        ✅ 剥
  - ``Q25111602DDXNEF001X-4060`` → 原样保留     ❌ 不剥（DDX 不存在）
  - ``J24070104SY0301--AREA150-J22082101`` → 原样   ❌ 不剥
  - ``KB8-001`` → 原样                          ❌ 已干净不动

用法
====
    # 看影响（不写库）
    PYTHONPATH=. .venv/bin/python scripts/normalize_shop_spec_code.py --dry-run

    # 真跑
    PYTHONPATH=. .venv/bin/python scripts/normalize_shop_spec_code.py

    # 只跑 shipment_lines 不跑 sku_master
    PYTHONPATH=. .venv/bin/python scripts/normalize_shop_spec_code.py --skip-sku-master
"""

from __future__ import annotations

import argparse
import json
import sys

sys.path.insert(0, ".")

from sqlalchemy.orm.attributes import flag_modified

from src.database import SessionLocal
from src.integrations.jackyun.mappers.shipment import _normalize_shop_spec_code
from src.planner import models


def normalize_shipment_lines(db, *, dry_run: bool) -> dict:
    """扫 shipment_lines.metadata.shop_spec_code，归一化拼装的脏值。"""
    rows = (
        db.query(models.ShipmentLine.id, models.ShipmentLine.metadata_json)
        .filter(
            models.ShipmentLine.is_archived.is_(False),
            models.ShipmentLine.metadata_json["shop_spec_code"].isnot(None),
        )
        .all()
    )
    total = 0
    changed = 0
    examples: list[dict] = []
    for row_id, meta in rows:
        if not isinstance(meta, dict):
            continue
        raw_code = str(meta.get("shop_spec_code") or "").strip()
        if not raw_code:
            continue
        total += 1
        normalized, raw_kept = _normalize_shop_spec_code(raw_code, db=db)
        if not normalized or normalized == raw_code:
            continue
        # 真有变化
        changed += 1
        if len(examples) < 8:
            examples.append({"id": str(row_id), "from": raw_code, "to": normalized})
        if not dry_run:
            new_meta = dict(meta)
            new_meta["shop_spec_code"] = normalized
            new_meta["shop_spec_code_raw"] = raw_kept or raw_code
            db.query(models.ShipmentLine).filter(models.ShipmentLine.id == row_id).update(
                {models.ShipmentLine.metadata_json: new_meta}, synchronize_session=False
            )
    if not dry_run and changed:
        db.commit()
    return {"scanned": total, "changed": changed, "examples": examples}


def normalize_sku_master(db, *, dry_run: bool) -> dict:
    """扫 sku_master.metadata.shop_spec_code，归一化。"""
    rows = (
        db.query(models.SkuMaster)
        .filter(
            models.SkuMaster.is_archived.is_(False),
            models.SkuMaster.metadata_json["shop_spec_code"].isnot(None),
        )
        .all()
    )
    total = 0
    changed = 0
    examples: list[dict] = []
    for sm in rows:
        meta = sm.metadata_json if isinstance(sm.metadata_json, dict) else None
        if not meta:
            continue
        raw_code = str(meta.get("shop_spec_code") or "").strip()
        if not raw_code:
            continue
        total += 1
        normalized, raw_kept = _normalize_shop_spec_code(raw_code, db=db)
        if not normalized or normalized == raw_code:
            continue
        changed += 1
        if len(examples) < 8:
            examples.append(
                {
                    "sku_code": sm.erp_sku_barcode,
                    "from": raw_code,
                    "to": normalized,
                }
            )
        if not dry_run:
            new_meta = dict(meta)
            new_meta["shop_spec_code"] = normalized
            new_meta["shop_spec_code_raw"] = raw_kept or raw_code
            sm.metadata_json = new_meta
            flag_modified(sm, "metadata_json")
    if not dry_run and changed:
        db.commit()
    return {"scanned": total, "changed": changed, "examples": examples}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="只看影响不写库")
    parser.add_argument("--skip-shipments", action="store_true")
    parser.add_argument("--skip-sku-master", action="store_true")
    args = parser.parse_args()

    db = SessionLocal()
    out: dict = {"dry_run": args.dry_run}
    try:
        if not args.skip_shipments:
            out["shipment_lines"] = normalize_shipment_lines(db, dry_run=args.dry_run)
        if not args.skip_sku_master:
            out["sku_master"] = normalize_sku_master(db, dry_run=args.dry_run)
    finally:
        db.close()

    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

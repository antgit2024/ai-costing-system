"""
测试期一次性脚本：按"模型编码 + spec_text 关键词"重置一批 SKU 的绑定状态。

适用场景
--------
当 picker 行为升级后，需要在测试环境从"干净状态"重新走人工绑定流程：
  1) 先把这一批 SKU 的 active 绑定关系清掉（不删历史，按
     product_model_service.unbind_sku 的语义置 is_active=False，类似 UI 上的"解绑"按钮）；
  2) 把 sku_master.metadata_json.bound_variant_code 也一并清掉，避免列表残留旧标签；
  3) 这样运营在 picker 里就能从"未绑定"开始重选 KB8-001 / KB8-002 等具体变体，
     验证变体编码是否正确落库 + 列表是否拼出 麻感冰丝(KB8-001) 这种二级标签。

不会做的事
----------
- 不删 SkuModelVersionMapping 历史行（is_active=False 即可，保留 effective_through）。
- 不删 SkuMaster 行本身。
- 不动 ShipmentLine 的快照。

用法
----
    # 干跑（默认）：列出会被影响的 SKU，不写库
    python -m scripts.reset_sku_bindings_for_test --model-code KB8 --spec-contains 冰丝凉感

    # 真正执行：加 --do
    python -m scripts.reset_sku_bindings_for_test --model-code KB8 --spec-contains 冰丝凉感 --do
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy.orm.attributes import flag_modified  # noqa: E402

from src.database import SessionLocal  # noqa: E402
from src.planner import models  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-code", required=True, help="模型编码（如 KB8）")
    parser.add_argument(
        "--spec-contains",
        default=None,
        help="可选：仅清 spec_text 含该子串的 SKU（如 冰丝凉感）；不传则清所有该模型已绑 SKU。",
    )
    parser.add_argument(
        "--do",
        action="store_true",
        help="不加该参数 = dry-run 仅打印；加上才真正写库。",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        model = (
            db.query(models.ProductModel)
            .filter(models.ProductModel.model_code == args.model_code)
            .first()
        )
        if not model:
            print(f"[fatal] model_code={args.model_code} 不存在")
            return 1

        v = (
            db.query(models.ProductModelVersion)
            .filter(
                models.ProductModelVersion.model_id == model.id,
                models.ProductModelVersion.version_status == "published",
                models.ProductModelVersion.is_archived.is_(False),
            )
            .first()
        )
        if not v:
            print(f"[fatal] model={args.model_code} 没有 published 版本")
            return 1

        print(
            f"[info] target model={model.model_code} ({model.id})  "
            f"published_version={v.version_label} ({v.id})"
        )

        active_maps = (
            db.query(models.SkuModelVersionMapping)
            .filter(
                models.SkuModelVersionMapping.model_version_id == v.id,
                models.SkuModelVersionMapping.is_active.is_(True),
                models.SkuModelVersionMapping.is_archived.is_(False),
            )
            .all()
        )
        sku_codes = [m.sku_code for m in active_maps]
        print(f"[info] active mapping 数: {len(active_maps)}")

        sm_rows = (
            db.query(models.SkuMaster)
            .filter(
                models.SkuMaster.erp_sku_barcode.in_(sku_codes),
                models.SkuMaster.is_archived.is_(False),
            )
            .all()
        )
        sm_by_code = {r.erp_sku_barcode: r for r in sm_rows}

        # spec_text 过滤
        if args.spec_contains:
            kw = args.spec_contains
            filtered = [code for code in sku_codes if kw in (sm_by_code.get(code).spec_text or "")]
        else:
            filtered = sku_codes

        print(f"[info] 过滤后待清条数: {len(filtered)}")
        for i, code in enumerate(filtered[:10]):
            sm = sm_by_code.get(code)
            print(f"  [{i+1}] {code}  spec={(sm.spec_text or '')[:60]!r}")
        if len(filtered) > 10:
            print(f"  ... 共 {len(filtered)} 条")

        if not args.do:
            print("[dry-run] 加 --do 才真正执行 unbind + clear bound_variant_code")
            return 0

        now_iso = datetime.now(timezone.utc).isoformat()
        unbound_mapping_count = 0
        cleared_meta_count = 0

        for code in filtered:
            # 1) deactivate mapping
            for m in active_maps:
                if m.sku_code != code:
                    continue
                m.is_active = False
                meta0 = m.metadata_json or {}
                meta0.setdefault("effective_through", now_iso)
                meta0["unbound_reason"] = "test_reset_script"
                m.metadata_json = meta0
                try:
                    flag_modified(m, "metadata_json")
                except Exception:
                    pass
                unbound_mapping_count += 1

            # 2) clear sku_master.metadata_json
            sm = sm_by_code.get(code)
            if not sm:
                continue
            meta = dict(sm.metadata_json or {})
            changed = False
            if "bound_variant_code" in meta:
                meta.pop("bound_variant_code", None)
                changed = True
            meta["binding_cleared_at"] = now_iso
            meta["binding_cleared_reason"] = "test_reset_script"
            meta.pop("model_bound_at", None)
            meta.pop("model_bound_by", None)
            meta.pop("model_binding_method", None)
            meta.pop("binding_validation_state", None)
            sm.metadata_json = meta
            try:
                flag_modified(sm, "metadata_json")
            except Exception:
                pass
            if changed:
                cleared_meta_count += 1

        db.commit()
        print(
            f"[done] 已 unbind mapping={unbound_mapping_count} 条，"
            f"清除 bound_variant_code 字段={cleared_meta_count} 条。"
        )
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())

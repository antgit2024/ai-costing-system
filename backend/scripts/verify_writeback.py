"""读回验证: 用 erp.storage.goodslist 查 sku, 看反写字段是否落库吉客云那边."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from src.integrations.jackyun.client import build_default_client  # noqa: E402

SKU_BARCODE = "6250070295093"
GOODS_NO = "J26051302"

client = build_default_client()
resp = client.call(
    "erp.storage.goodslist",
    {"pageIndex": 0, "pageSize": 50, "goodsNos": [GOODS_NO]},
)
print(f"success={resp.success} sub={resp.biz_sub_code}")
data = resp.data if isinstance(resp.data, dict) else {}
goods = data.get("goods") or []
if not goods:
    print("⚠️ 未查到 goods, 原始 data:")
    print(json.dumps(data, ensure_ascii=False, indent=2)[:800])
    sys.exit(0)
for g in goods:
    sku_list = g.get("skuList") or [g]  # 兜底, 有的接口扁平返回
    for sku in sku_list:
        if str(sku.get("skuBarcode")) != SKU_BARCODE:
            continue
        print("--- 吉客云回读: 命中 sku 全部 key ---")
        sku_field_keys = [k for k in sku.keys() if k.startswith("skuField") or k.startswith("goodsField")]
        print(f"  skuField*/goodsField* 全 keys: {sku_field_keys}")
        print(f"  flagData: {sku.get('flagData')!r}")
        print(f"  skuName: {sku.get('skuName')!r}")
        print(f"  skuGmtModified: {sku.get('skuGmtModified')!r}")
        for k in sku_field_keys:
            print(f"  {k}: {sku.get(k)!r}")
        # 完整 dump 找 OZU-004 字串
        full = json.dumps(sku, ensure_ascii=False)
        if "OZU-004" in full:
            print(f"  ⭐ raw 含 'OZU-004' 字符串 -> 写入成功, 但不在 skuField1 字段")
        else:
            print(f"  ❌ raw 不含 'OZU-004' -> 写入未生效 (或读接口不返回此字段)")

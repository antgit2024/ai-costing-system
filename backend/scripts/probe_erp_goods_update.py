"""探针: 用不同 biz 结构反复调 erp.goods.update, 缩小 JSON 解析错误的根因.

判定规则:
- subCode = 0030099001 (JSON 解析错误) → biz schema / 包装层错了
- subCode = 0030020310 (未订阅 API)    → 接口名 / 订阅问题
- subCode = 0030000004 / 0           → 成功
- 其他业务错误 (缺必填 / 字段名错)        → 结构基本对了, 接近答案
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# 让脚本能被 .venv/bin/python 直接跑: 把 backend 加进 sys.path,
# 然后用 src.xxx 的完整路径 import (与 uvicorn src.main:app 一致).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from src.integrations.jackyun.client import build_default_client  # noqa: E402
from src.integrations.base.errors import IntegrationError  # noqa: E402

GOODS_NO = "J26051302"
SKU_BARCODE = "6250070295093"
GOODS_ID = "2478546728242972416"
SKU_ID = "2480741003834000512"

# 用户截图: 批量更新商品档案接口 = erp-goods-online.item.batchupdateitem
# biz 用 inputItemList wrap, sku 字段挂 skuList[N]
BATCH_BIZ = {
    "inputItemList": [
        {
            "goodsNo": GOODS_NO,
            "skuList": [
                {
                    "skuBarcode": SKU_BARCODE,
                    "skuField1": "OZU-004",
                }
            ],
        }
    ]
}

# erp.goods.update 已确认是真接口 (其他都报 0130020310 未订阅).
# 现在专注探 biz schema, JSON解析错通常意味着缺必填字段或顶层 wrap 不对.
# 业内常见三种风格: data wrap / goods wrap / list wrap.
# biz 顶层就是 array of goods — 这是 erp.goods.update 的关键发现!
# 现在确认 sku 字段如何挂 + 读回验证.
# 真正的 sku 字段反写接口! 经官方 doc 拉取确认:
# - 顶层是 array, 每个对象是一个 sku 行 (平铺, 无 skuList wrap)
# - 必填: goodsName / goodsNo / unitName / outSkuCode
# - 含 goodsField1..50 (货品自定义) + skuField1..30 (规格自定义)
# - 是 upsert 还是只 insert? 现在实测
NEW_API = "erp.goods.skuimportbatch"

# skuimportbatch 是 UPSERT! 匹配键是 outSkuCode (官方文档 2026-05-11 更新)
# 当前 sku 的 outSkuCode 是 null, 第一次推送要"锚定": 用稳定 ID 当 outSkuCode
# + 不传 skuBarcode (避免条码冲突), goodsNo + skuName 让吉客云定位现有规格
SPEC_NAME = "J26051302C科技皮沥水垫 躺平猫咪;50*80cm"
GOODS_NAME = "猫咪厨房沥水垫台面保护垫吸水垫桌垫隔热垫餐垫咖啡机垫2026新款"

METHOD_CASES = [
    # A: 用 skuBarcode 当 outSkuCode, 不传 skuBarcode 字段
    (NEW_API, [{
        "goodsNo": GOODS_NO,
        "goodsName": GOODS_NAME,
        "unitName": "件",
        "outSkuCode": SKU_BARCODE,  # 锚定外部码 = 条码
        "skuName": SPEC_NAME,
        "skuField1": "OZU-IMPORT-A1",
        "skuField8": "工艺-IMPORT-A1",
    }]),
    # B: 用 erp_sku_id 当 outSkuCode (一定唯一)
    (NEW_API, [{
        "goodsNo": GOODS_NO,
        "goodsName": GOODS_NAME,
        "unitName": "件",
        "outSkuCode": f"SM-{SKU_ID}",  # 加前缀避免和别的系统冲突
        "skuName": SPEC_NAME,
        "skuField1": "OZU-IMPORT-B1",
        "skuField8": "工艺-IMPORT-B1",
    }]),
]


def main() -> None:
    client = build_default_client()
    for method, biz in METHOD_CASES:
        print("=" * 70)
        print(f"method: {method}")
        print(f"biz: {json.dumps(biz, ensure_ascii=False)[:200]}")
        try:
            resp = client.call(method, biz)
            print(f"  success={resp.success} sub={resp.biz_sub_code} msg={resp.message!r}")
            print(json.dumps(resp.raw, ensure_ascii=False, indent=2))
        except IntegrationError as e:
            print(f"  ❌ sub={getattr(e, 'biz_sub_code', None)} err={e}")
        except IntegrationError as e:
            sub = getattr(e, "biz_sub_code", None)
            tag = "❌"
            if sub == "0130020310":
                tag = "🚫 接口名错 / 未订阅"
            elif sub == "0030099001":
                tag = "🟡 JSON解析错(可能 biz 错, 但接口名存在)"
            print(f"  {tag} sub_code={sub} err={e}")
        except Exception as e:  # noqa: BLE001
            print(f"  💥 {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()

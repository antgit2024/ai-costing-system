"""重新调 erp.goods.customfield, dump 完整原始 response, 找真实 fieldName.

之前误把 skuFieldN 当 fieldName, 实际文档显示 fieldName 形如
'extend835999132354228992'. 这是 sku/goods 字段反写失败的根因.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from src.integrations.jackyun.client import build_default_client  # noqa: E402

client = build_default_client()
# 文档说 bizdata 是"无数据", 直接空对象
resp = client.call("erp.goods.customfield", {})
print(f"success={resp.success} biz_code={resp.biz_code} sub_code={resp.biz_sub_code}")
print(f"msg: {resp.message}")
print("--- 完整 RAW ---")
print(json.dumps(resp.raw, ensure_ascii=False, indent=2))

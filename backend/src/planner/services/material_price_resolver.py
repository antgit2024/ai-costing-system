"""Stage 2 物料取价 / 含税还原 / 数据质量分级 解析器

Stage 2（migration 0039 + commit e6dcf969）给 ``materials`` 表加了 6 个字段：

- ``purchase_entity_id`` 采购法人（v1 枚举字符串）
- ``tax_included_flag``  unit_price 是否含税（默认 False）
- ``tax_rate``            税率（0.0~1.0）
- ``price_source``       价格来源（contract / invoice / purchase_order / manual / estimate / ...）
- ``effective_from``     生效期（NULL 视为立即生效）
- ``effective_to``       失效期（NULL 视为当前仍有效）

加完字段后**核心 BOM 计算 service 完全没读这些字段**——加了等于没加。本模块就是
"真正接入"的中央取价器：所有用到物料 unit_price 的地方都应该走 ``resolve_material_price()``，
保证每个物料行都得到：

1. **生效期取价**：``as_of_date`` 落入 ``[effective_from, effective_to]`` 才算有效；
   老数据 ``effective_from`` = NULL 视为永久生效（向后兼容）
2. **含税还原**：成本核算用不含税价（法定要求）；``tax_included_flag=True`` 时
   ``price_exclusive = price_inclusive / (1 + tax_rate)``
3. **数据质量分级**：green / yellow / red，让前端用 emoji 让老板一眼判断准确度

设计准则（写死，不再讨论）
-------------------------
- 不报错就 fallback：老数据全 NULL 时回到 ``unit_price`` 直读，``data_quality=yellow``
  + ``warnings`` 加一条说明，但**不抛异常**（核心 BOM 路径不许 break）
- ``tax_rate=NULL`` 兜底：v1 写死 13%（一般纳税人主流），data_quality 降为 yellow
  （未来 Phase 2 看 ``purchase_entity_id`` 自动推断，1 行 if 即可）
- 价格永远是 BOM 单位下的"不含税价"：
  ``price_exclusive_per_bom_unit = (unit_price ÷ (1+tax_rate if tax_included else 1))
                                  ÷ conversion_purchase_to_bom``
- 返回结构同时给"含税"和"不含税"两个 Decimal，前端展示含税价（用户习惯），
  成本核算用不含税价（法定）

验收：``backend/tests/planner/test_material_price_resolver.py`` 8 条测试全过。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional

from .. import models


# v1 兜底税率：tax_rate IS NULL 时假设。13% = 一般纳税人主流（家具/装饰板材/包装等）。
# 未来按 purchase_entity_id 推断（一般纳税人 13% / 小规模 3%）走这里改 1 行即可。
DEFAULT_TAX_RATE_FALLBACK: Decimal = Decimal("0.13")


# 价格来源质量排序，多版本时优先取高质量来源（contract > invoice > purchase_order > manual > estimate）
PRICE_SOURCE_QUALITY_RANK: Dict[str, int] = {
    "contract": 100,
    "invoice": 90,
    "po_avg_30d": 80,
    "purchase_order": 80,
    "manual": 50,
    "estimate": 30,
}


# 中文化展示用，前端 tooltip / 列展示直接用
PRICE_SOURCE_LABELS_CN: Dict[str, str] = {
    "contract": "合同",
    "invoice": "发票",
    "po_avg_30d": "采购近 30 天均价",
    "purchase_order": "采购单",
    "manual": "手填",
    "estimate": "估算",
}


def price_source_label_cn(code: str | None) -> str:
    if not code:
        return "未填"
    return PRICE_SOURCE_LABELS_CN.get(str(code).lower(), str(code))


@dataclass
class MaterialPriceQuote:
    """``resolve_material_price`` 的返回结构。

    所有字段都对应 ``cost_breakdown.materials[].price_metadata`` 的 JSON 形态。
    """

    price_inclusive: Optional[Decimal] = None
    """含税价（每个 purchase_unit）。tax_included_flag=False 时与 price_exclusive 相等。"""

    price_exclusive: Optional[Decimal] = None
    """不含税价（每个 purchase_unit）—— 成本核算法定用这个。"""

    bom_unit_price_exclusive: Optional[Decimal] = None
    """不含税价（每个 BOM 单位）—— 替代老 ``_derive_bom_unit_price`` 的返回值。"""

    tax_rate: Optional[Decimal] = None
    """实际生效的税率（兜底后的，不一定等于 ``material.tax_rate``）。"""

    tax_included_flag: bool = False

    purchase_entity_id: Optional[str] = None

    price_source: Optional[str] = None

    effective_from: Optional[date] = None

    effective_to: Optional[date] = None

    data_quality: str = "yellow"
    """green / yellow / red — 见模块顶部注释。"""

    warnings: List[str] = field(default_factory=list)

    def to_jsonable(self) -> Dict[str, Any]:
        """转换为可写进 cost_breakdown.materials[].price_metadata 的 dict。

        Decimal -> float（JSONB 友好），date -> ISO string。
        """

        def _f(v: Optional[Decimal]) -> Optional[float]:
            return None if v is None else float(v)

        return {
            "price_inclusive": _f(self.price_inclusive),
            "price_exclusive": _f(self.price_exclusive),
            "bom_unit_price_exclusive": _f(self.bom_unit_price_exclusive),
            "tax_rate": _f(self.tax_rate),
            "tax_included_flag": bool(self.tax_included_flag),
            "purchase_entity_id": self.purchase_entity_id,
            "price_source": self.price_source,
            "effective_from": self.effective_from.isoformat() if self.effective_from else None,
            "effective_to": self.effective_to.isoformat() if self.effective_to else None,
            "_data_quality": self.data_quality,
            "_warnings": list(self.warnings),
        }


def _to_decimal(value: Any) -> Optional[Decimal]:
    if value in (None, ""):
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except Exception:  # noqa: BLE001
        return None


def _is_within_period(
    *, as_of: date, effective_from: Optional[date], effective_to: Optional[date]
) -> bool:
    """``as_of`` 是否落入 [effective_from, effective_to] 区间。

    NULL 端视为开放：老数据 ``effective_from=None`` 表示"永远生效"，
    ``effective_to=None`` 表示"至今仍有效"。
    """

    if effective_from is not None and as_of < effective_from:
        return False
    if effective_to is not None and as_of > effective_to:
        return False
    return True


def resolve_material_price(
    material: models.Material,
    *,
    as_of_date: Optional[date] = None,
    purchase_entity_id: Optional[str] = None,
) -> MaterialPriceQuote:
    """Stage 2 取价中央实现。

    Parameters
    ----------
    material : Material ORM
        要取价的物料行。
    as_of_date : date | None
        生效期判断基准日，默认今天。发货行回溯时应传发货日（精确还原）。
    purchase_entity_id : str | None
        预留：未来按主体过滤候选（v1 不实现，因为 materials 表只有 1 行/物料）。

    取价规则（按优先级）
    -------------------
    1. 如果 ``effective_from`` 不为 NULL：
       - ``as_of_date`` 必须落在 ``[effective_from, effective_to]``，否则视为无效，
         data_quality=yellow + warning（仍返回 unit_price 兜底，避免成本算成 0）
    2. 如果 ``effective_from`` 为 NULL（老数据）：
       - 直接用当前 unit_price，data_quality 默认 yellow（缺失元数据）
    3. 如果 unit_price 也缺：data_quality=red, price=None

    含税还原
    --------
    - ``tax_included_flag=True`` 且有 tax_rate：
      ``price_exclusive = price_inclusive / (1 + tax_rate)``
    - ``tax_included_flag=True`` 但 tax_rate=NULL：默认 13%，data_quality 降级为 yellow
    - ``tax_included_flag=False``：``price_exclusive = price_inclusive`` (unit_price 即不含税价)
    """

    if as_of_date is None:
        as_of_date = date.today()

    quote = MaterialPriceQuote(
        purchase_entity_id=getattr(material, "purchase_entity_id", None),
        price_source=getattr(material, "price_source", None),
        effective_from=getattr(material, "effective_from", None),
        effective_to=getattr(material, "effective_to", None),
        tax_included_flag=bool(getattr(material, "tax_included_flag", False)),
    )

    unit_price = _to_decimal(getattr(material, "unit_price", None))

    if unit_price is None or unit_price <= 0:
        quote.data_quality = "red"
        quote.warnings.append("material.unit_price 缺失或非正，无法取价")
        return quote

    if quote.effective_from is not None or quote.effective_to is not None:
        if not _is_within_period(
            as_of=as_of_date,
            effective_from=quote.effective_from,
            effective_to=quote.effective_to,
        ):
            quote.data_quality = "yellow"
            quote.warnings.append(
                "as_of_date={as_of} 不在生效期 [{ef}, {et}] 内，使用兜底当前价".format(
                    as_of=as_of_date.isoformat(),
                    ef=quote.effective_from.isoformat() if quote.effective_from else "-",
                    et=quote.effective_to.isoformat() if quote.effective_to else "-",
                )
            )
        else:
            quote.data_quality = "green"
    else:
        quote.data_quality = "yellow"
        quote.warnings.append("material.effective_from 缺失，按当前 unit_price 永久生效")

    raw_tax_rate = _to_decimal(getattr(material, "tax_rate", None))
    if quote.tax_included_flag:
        if raw_tax_rate is not None:
            quote.tax_rate = raw_tax_rate
        else:
            quote.tax_rate = DEFAULT_TAX_RATE_FALLBACK
            quote.data_quality = "yellow" if quote.data_quality == "green" else quote.data_quality
            quote.warnings.append(
                f"tax_included_flag=True 但 tax_rate 缺失，按默认 {DEFAULT_TAX_RATE_FALLBACK*100:.0f}% 兜底"
            )
        quote.price_inclusive = unit_price
        if quote.tax_rate is not None and quote.tax_rate >= 0:
            quote.price_exclusive = unit_price / (Decimal("1") + quote.tax_rate)
        else:
            quote.price_exclusive = unit_price
    else:
        quote.tax_rate = raw_tax_rate
        quote.price_exclusive = unit_price
        if raw_tax_rate is not None and raw_tax_rate > 0:
            quote.price_inclusive = unit_price * (Decimal("1") + raw_tax_rate)
        else:
            quote.price_inclusive = unit_price

    if not quote.price_source:
        quote.warnings.append("price_source 缺失，无法判断价格可靠度")
        if quote.data_quality == "green":
            quote.data_quality = "yellow"

    conversion = _to_decimal(getattr(material, "conversion_purchase_to_bom", None))
    bom_unit = (getattr(material, "unit", "") or "").strip()
    purchase_unit = (getattr(material, "purchase_unit", "") or "").strip()
    if quote.price_exclusive is not None and conversion is not None and conversion > 0:
        quote.bom_unit_price_exclusive = quote.price_exclusive / conversion
        if not bom_unit or not purchase_unit:
            if quote.data_quality == "green":
                quote.data_quality = "yellow"
            quote.warnings.append(
                "BOM/采购单位字符串缺失（unit/purchase_unit），按 conversion 系数照常换算 BOM 单价"
            )
    elif quote.price_exclusive is not None:
        quote.bom_unit_price_exclusive = None
        quote.warnings.append(
            "conversion_purchase_to_bom 缺失或<=0，无法换算 BOM 单价"
        )

    return quote


def derive_bom_unit_price_exclusive(
    material: models.Material,
    *,
    as_of_date: Optional[date] = None,
) -> Optional[Decimal]:
    """老 ``_derive_bom_unit_price`` 的 Stage 2 兼容入口。

    返回**不含税** BOM 单价 Decimal（与老接口签名一致）。所有现有调用点保持不变，
    把 ``unit_price`` 直读切换到这里就自动获得：含税还原 + 生效期取价 + 数据质量降级。

    Behaviour matrix
    ----------------
    | tax_included | tax_rate | unit_price | -> bom_unit_price_exclusive |
    | False        | -        | 100        | 100 / conversion            |
    | True         | 0.13     | 113        | 100 / conversion            |
    | True         | NULL     | 113        | 100 / conversion (default 13%) |
    | -            | -        | 0/NULL     | None                        |
    """

    quote = resolve_material_price(material, as_of_date=as_of_date)
    return quote.bom_unit_price_exclusive

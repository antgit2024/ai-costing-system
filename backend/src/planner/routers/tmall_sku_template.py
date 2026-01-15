from __future__ import annotations

import io
from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

router = APIRouter(prefix="/tmall/sku-template", tags=["tmall"])


# -----------------------------
# Schemas (MVP)
# -----------------------------


class TmallSizeOption(BaseModel):
    key: str = Field(..., description="尺寸key（内部唯一，例如 size_1）")
    label: str = Field(..., description="尺寸展示值（例如：枕套 / 枕芯+枕套）")
    # Optional per-size defaults
    size_code: Optional[str] = Field(None, description="用于商家编码的尺寸段（例如 C1/C2）")


class TmallColorOption(BaseModel):
    key: str = Field(..., description="颜色分类key（内部唯一）")
    label: str = Field(..., description="颜色分类展示值（天猫语义=图案/工艺/款式）")
    width_cm: Optional[float] = Field(None, description="宽(cm)")
    height_cm: Optional[float] = Field(None, description="高(cm)")
    thickness_cm: Optional[float] = Field(None, description="厚度(cm)")
    length_cm: Optional[float] = Field(None, description="长度(cm)")
    main_pattern_type: Optional[str] = Field(None, description="主图案类型（可选）")


class TmallSkuCell(BaseModel):
    color_key: str
    size_key: str
    enabled: bool = True
    # Optional override
    merchant_sku: Optional[str] = None


class TmallSkuTemplateRequest(BaseModel):
    # Basic
    sizes: List[TmallSizeOption]
    colors: List[TmallColorOption]
    cells: List[TmallSkuCell]
    # Defaults
    default_enabled: bool = True
    default_sku_status: int = 1

    # Merchant SKU generator (simple MVP)
    merchant_sku_prefix: str = Field("", description="商家编码前缀，例如 BZPB008XXXXX-")
    merchant_sku_sep: str = Field("-", description="分隔符")
    merchant_sku_suffix: str = Field("", description="商家编码后缀（可选）")


class TmallSkuRow(BaseModel):
    color_label: str
    size_label: str
    merchant_sku: str
    sku_status: int
    main_pattern_type: Optional[str] = None
    length_cm: Optional[str] = None
    thickness_cm: Optional[str] = None
    width_cm: Optional[str] = None


class TmallSkuTemplatePreviewResponse(BaseModel):
    total_rows: int
    rows: List[TmallSkuRow]
    # Sheet2 mapping (for transparency)
    header_mapping: Dict[str, str]


TMALL_SHEET2_MAPPING: Dict[str, str] = {
    "颜色分类": "p-1627207",
    "尺寸": "p-21433",
    "商家编码": "skuOuterId",
    "是否上架": "skuStatus",
    "主图案类型": "skuParam_p-20603",
    "长度": "skuParam_p-554361099",
    "厚度(cm)": "skuParam_p-554360987",
    "宽度": "skuParam_p-554668632",
}


def _fmt_num(v: Optional[float]) -> Optional[str]:
    if v is None:
        return None
    try:
        n = float(v)
    except Exception:
        return None
    if n != n:  # NaN
        return None
    # keep up to 2 decimals, strip trailing zeros
    s = f"{n:.2f}"
    s = s.rstrip("0").rstrip(".")
    return s


def _build_preview_rows(payload: TmallSkuTemplateRequest) -> List[TmallSkuRow]:
    size_by_key: Dict[str, TmallSizeOption] = {s.key: s for s in payload.sizes}
    color_by_key: Dict[str, TmallColorOption] = {c.key: c for c in payload.colors}

    rows: List[TmallSkuRow] = []

    for cell in payload.cells:
        c = color_by_key.get(cell.color_key)
        s = size_by_key.get(cell.size_key)
        if not c or not s:
            continue

        enabled = bool(cell.enabled)
        sku_status = 1 if enabled else 0

        # Merchant sku (MVP): prefix + WxH + size_code + suffix
        if cell.merchant_sku:
            merchant = str(cell.merchant_sku).strip()
        else:
            w = _fmt_num(c.width_cm) or ""
            h = _fmt_num(c.height_cm) or ""
            wh = ""
            if w and h:
                wh = f"{w}{h}"
            code = str(s.size_code or "").strip()
            merchant = f"{payload.merchant_sku_prefix}{wh}{code}{payload.merchant_sku_suffix}"
            merchant = merchant.strip() or ""

        rows.append(
            TmallSkuRow(
                color_label=c.label,
                size_label=s.label,
                merchant_sku=merchant,
                sku_status=sku_status,
                main_pattern_type=(c.main_pattern_type or None),
                length_cm=_fmt_num(c.length_cm),
                thickness_cm=_fmt_num(c.thickness_cm),
                width_cm=_fmt_num(c.width_cm),
            )
        )

    return rows


@router.post("/preview", response_model=TmallSkuTemplatePreviewResponse)
def preview_tmall_sku_template(payload: TmallSkuTemplateRequest) -> TmallSkuTemplatePreviewResponse:
    rows = _build_preview_rows(payload)
    return TmallSkuTemplatePreviewResponse(total_rows=len(rows), rows=rows, header_mapping=TMALL_SHEET2_MAPPING)


@router.post("/export")
def export_tmall_sku_template(payload: TmallSkuTemplateRequest) -> StreamingResponse:
    from openpyxl import Workbook

    rows = _build_preview_rows(payload)

    wb = Workbook(write_only=True)

    # Sheet1: data
    ws = wb.create_sheet("sheet1")
    headers = ["颜色分类", "尺寸", "商家编码", "是否上架", "主图案类型", "长度", "厚度(cm)", "宽度"]
    ws.append(headers)
    for r in rows:
        ws.append(
            [
                r.color_label,
                r.size_label,
                r.merchant_sku,
                str(r.sku_status),
                r.main_pattern_type or "",
                r.length_cm or "",
                r.thickness_cm or "",
                r.width_cm or "",
            ]
        )

    # Sheet2: mapping
    ws2 = wb.create_sheet("sheet2")
    ws2.append(["字段名", "平台字段key"])
    for k, v in TMALL_SHEET2_MAPPING.items():
        ws2.append([k, v])

    bio = io.BytesIO()
    wb.save(bio)
    bio.seek(0)

    filename = "tmall_buyi_sku_template.xlsx"
    headers: Dict[str, Any] = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(
        bio,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )


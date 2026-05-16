"""Jackyun ERP goods master Excel importer.

Blueprint: ``DOC/costing/blueprints/jackyun_erp_goods_master_sync_backlog.md``
Template:  ``DOC/基础表单/吉客云货品档案导入模板规范_v1.md``

Why a new file (rather than extending ``sku_master_service.import_erp_sku_master_xlsx``):
- The legacy importer's header set is "shop/online" oriented (`商品规格（网店）`,
  `规格编码（网店）`, etc.) and loads the whole workbook into memory via openpyxl.
- This importer targets the **Jackyun ERP goods master** export (~43 万行 / 950 MB
  uncompressed XML) so it MUST be streaming (``iterparse``) + batch-committed
  (5000 rows / tx) to avoid OOM.
- Different header set, different mapping semantics, different size profile → new file.

Three modes:
- ``inspect_xlsx``:   read header row only; return identified mapping + unmatched cols
- ``dry_run``:        full stream parse, simulate upsert, return diff report; **no DB write**
- ``import_commit``:  same as dry_run but actually commits in 5000-row batches

Overwrite policy: **narrow overwrite** — only fields whose source columns appear in the
final mapping (after user override) are touched on existing rows. Fields not in the
mapping are left intact (e.g. system-side ``production_process``, ``sku_flag``).

Compatible with Postgres (production) and SQLite (tests). No pandas / openpyxl
required at runtime.
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Optional, Tuple
from xml.etree import ElementTree as ET

from sqlalchemy.orm import Session

from .. import models
from .sku_master_service import _norm_str, _parse_excel_datetime, _utcnow


# ---------------------------------------------------------------------------
# Column identification — candidate names → target field
# ---------------------------------------------------------------------------

# Each entry: ``target field`` (== mapping key) → list of candidate Chinese names
# the importer auto-recognizes from the Excel header row. First match wins.
#
# Target field naming:
#   - bare name (``barcode``, ``goods_no``, …): scalar value placed at top-level
#     in the row payload, dispatched to physical columns or metadata.erp.* by
#     ``_apply_row_payload``.
#   - ``metadata.erp.X``: pseudo-target documenting "this field lands in
#     ``sku_master.metadata_json['erp'][X]``".  ``_apply_row_payload`` reads
#     ``METADATA_ERP_FIELDS`` to know which scalar fields go to metadata.erp.
#
# Add new candidate names here as Jackyun introduces / renames columns.
CANDIDATE_NAMES: Dict[str, List[str]] = {
    # --- 主键 / 锚点 ---
    "erp_sku_barcode": ["条码", "货品条码", "SKU条码", "barcode"],
    "out_sku_code": ["外部编码", "外部货品编码", "outSkuCode", "商家编码"],
    "erp_goods_id": ["货品ID", "货品Id", "goodsId"],
    "erp_sku_id": ["规格ID", "规格Id", "skuId"],
    "spec_no": ["规格编号", "skuNo"],  # → metadata.erp.sku_no
    # --- 基础属性 ---
    "product_name": ["货品名称", "商品名称", "goodsName"],
    "product_code": ["货品编号", "goodsNo"],
    "spec_text": ["规格", "规格名称", "skuName"],
    "category": ["分类", "分类名称", "cateName"],  # → metadata.erp.category
    "category_full": ["分类全称", "cateFullName"],  # → metadata.erp.category_full
    "owner": ["货主", "货主名称", "ownerName"],  # → metadata.erp.owner
    "warehouse": ["默认存放仓库", "warehouseName"],  # → metadata.erp.warehouse
    "unit": ["单位", "unitName", "计量单位"],  # → metadata.erp.unit
    "memo": ["备注", "货品备注", "goodsMemo"],  # → metadata.erp.memo
    "sku_memo": ["规格备注", "memo"],  # → metadata.erp.sku_memo
    # --- 主条码 / 状态 / 标记 ---
    "main_barcode": ["主条码", "mainBarcode"],  # → metadata.erp.main_barcode
    "is_blocked": ["停用", "是否停用", "isBlockup", "货品是否停用"],
    "is_deleted_at_source": ["是否删除", "isDelete"],
    "flags": ["货品标记", "flagData", "goodsFlag"],  # → metadata.erp.flags (array)
    "sku_flag_synced": ["规格标记", "skuFlag"],  # → metadata.erp.sku_flag_synced (array,
    #                                              shadow; do NOT overwrite local sku_flag)
    # --- 反写目标字段（ERP 端值，落 metadata 镜像）---
    "process_instructions_reg": [
        "工艺说明(规)",
        "工艺说明（规）",
        "工艺说明",
        "process_instructions",
    ],  # → metadata.erp.process_instructions_reg
    "model_code_reg": [
        "模型编码(规)",
        "模型编码（规）",
        "模型编码",
        "model_code",
    ],  # → metadata.erp.model_code_reg
    "process_code_reg": [
        "工艺编码(规)",
        "工艺编码（规）",
        "工艺编码",
    ],  # → metadata.erp.process_code_reg
    "applicable_model_reg": [
        "适用模型(规)",
        "适用模型（规）",
        "适用模型",
    ],  # → metadata.erp.applicable_model_reg
    # --- 物理属性 ---
    "length": ["长", "skuLength"],  # → metadata.erp.dims.length
    "width": ["宽", "skuWidth"],  # → metadata.erp.dims.width
    "height": ["高", "skuHeight"],  # → metadata.erp.dims.height
    "weight_g": ["重量(g)", "重量（g）", "skuWeight"],  # → metadata.erp.dims.weight_g
    "weight_kg": ["重量"],  # → metadata.erp.dims.weight_kg
    "volume": ["体积", "volume"],  # → metadata.erp.dims.volume
    # --- 商品属性 ---
    "color": ["颜色", "colorName"],  # → metadata.erp.color
    "size": ["尺码", "sizeName"],  # → metadata.erp.size
    "abc_cate": ["ABC分类", "abcCate"],  # → metadata.erp.abc_cate
    "unit_rate": ["入库换算(规)", "入库换算"],  # → metadata.erp.unit_rate
    # --- 图片 / 链接 ---
    "product_image": ["货品主图链接", "货品主图", "mainGoodsUrl"],  # → images.product_image
    "spec_image": ["规格图片链接", "规格图片", "skuImgUrl"],  # → images.spec_image
    "image_top": ["上图链接"],  # → images.top
    "image_bottom": ["下图链接"],  # → images.bottom
    "image_left": ["左图链接"],  # → images.left
    "image_right": ["右图链接"],  # → images.right
    "url": ["链接", "url"],  # → metadata.erp.url
    # --- 时间 / 价格 ---
    "source_updated_at": ["最后修改时间", "修改时间", "gmtModified"],
    "created_at_at_source": ["建档时间", "gmtCreate"],  # → metadata.erp.created_at
    "fixed_cost_price": [
        "固定成本价",
        "retailPrice",
        "fixPrice",
    ],  # → metadata.erp.fixed_cost_price
}

# Fields above whose value lands in ``sku_master.metadata_json['erp'][...]`` instead
# of physical columns. Keys here must match the keys in CANDIDATE_NAMES.
METADATA_ERP_FIELDS = {
    "spec_no",
    "category",
    "category_full",
    "owner",
    "warehouse",
    "unit",
    "memo",
    "sku_memo",
    "main_barcode",
    "flags",
    "sku_flag_synced",
    "process_instructions_reg",
    "model_code_reg",
    "process_code_reg",
    "applicable_model_reg",
    "color",
    "size",
    "abc_cate",
    "unit_rate",
    "url",
    "created_at_at_source",
    "fixed_cost_price",
}

# Image fields → consolidated into sku_master.images_json.
IMAGE_FIELDS = {
    "product_image": "product_image",
    "spec_image": "spec_image",
    "image_top": "top",
    "image_bottom": "bottom",
    "image_left": "left",
    "image_right": "right",
}

# Dimension fields → metadata.erp.dims.{key}
DIMENSION_FIELDS = {
    "length": "length",
    "width": "width",
    "height": "height",
    "weight_g": "weight_g",
    "weight_kg": "weight_kg",
    "volume": "volume",
}

# Physical columns on sku_master (anything not in METADATA / IMAGE / DIMENSION).
PHYSICAL_COLUMN_TARGETS = {
    "erp_sku_barcode",
    "out_sku_code",
    "erp_goods_id",
    "erp_sku_id",
    "product_name",
    "product_code",
    "spec_text",
    "is_blocked",
    "is_deleted_at_source",
    "source_updated_at",
}

# Required target fields — without these the row is rejected.
REQUIRED_TARGETS = {"erp_sku_barcode"}

# Array fields whose Excel value is a delimited string ("爆款,新品" or "x;y"),
# stored as JSON array under metadata.erp.<key>.
ARRAY_FIELDS = {"flags", "sku_flag_synced"}


# ---------------------------------------------------------------------------
# Streaming XLSX parser (handles inline strings, ~950 MB single sheet)
# ---------------------------------------------------------------------------

_NS_A = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_TAG_ROW = f"{{{_NS_A}}}row"
_TAG_CELL = f"{{{_NS_A}}}c"
_TAG_VALUE = f"{{{_NS_A}}}v"
_TAG_INLINESTR = f"{{{_NS_A}}}is"
_TAG_TEXT = f"{{{_NS_A}}}t"


def _col_letters_to_idx(ref: str) -> int:
    """Convert 'A' / 'AA' style column ref (cell ref minus row digits) to 0-based index."""
    letters = ""
    for ch in ref:
        if ch.isalpha():
            letters += ch
        else:
            break
    idx = 0
    for ch in letters:
        idx = idx * 26 + (ord(ch.upper()) - ord("A") + 1)
    return idx - 1


def _load_shared_strings(zf: zipfile.ZipFile) -> List[str]:
    """Load xl/sharedStrings.xml into a list. Empty if absent (workbook uses inline strings)."""
    try:
        with zf.open("xl/sharedStrings.xml") as f:
            root = ET.parse(f).getroot()
    except KeyError:
        return []
    shared: List[str] = []
    for si in root.findall(f"{{{_NS_A}}}si"):
        parts = [tt.text or "" for tt in si.iter(_TAG_TEXT)]
        shared.append("".join(parts))
    return shared


def _cell_value(c: ET.Element, shared: List[str]) -> str:
    """Extract a textual value from a worksheet cell element."""
    t = c.attrib.get("t")
    if t == "inlineStr":
        is_el = c.find(_TAG_INLINESTR)
        if is_el is None:
            return ""
        return "".join((tt.text or "") for tt in is_el.iter(_TAG_TEXT))
    v = c.find(_TAG_VALUE)
    if v is None:
        return ""
    if t == "s":
        try:
            idx = int(v.text or "")
        except ValueError:
            return ""
        return shared[idx] if 0 <= idx < len(shared) else ""
    return v.text or ""


def _iter_rows(file_bytes: bytes) -> Iterator[Tuple[int, List[str]]]:
    """Stream-iterate worksheet rows.

    Yields ``(row_idx_1based, list_of_str_values)`` for every non-empty row.
    Header row is yielded as row_idx == 1; data rows start at 2.
    """
    with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
        shared = _load_shared_strings(zf)
        # First worksheet (matches "sheetTitle" in Jackyun exports)
        sheet_name = next(
            (n for n in zf.namelist() if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")),
            None,
        )
        if sheet_name is None:
            return
        with zf.open(sheet_name) as f:
            row_count = 0
            max_col_seen = 0
            for ev, elem in ET.iterparse(f, events=("end",)):
                if elem.tag != _TAG_ROW:
                    continue
                row_count += 1
                cell_map: Dict[int, str] = {}
                for c in elem.findall(_TAG_CELL):
                    ref = c.attrib.get("r", "")
                    if not ref:
                        continue
                    cidx = _col_letters_to_idx(ref)
                    if cidx < 0:
                        continue
                    val = _cell_value(c, shared)
                    if val != "":
                        cell_map[cidx] = val
                        if cidx > max_col_seen:
                            max_col_seen = cidx
                row_values = [cell_map.get(i, "") for i in range(max_col_seen + 1)]
                elem.clear()
                yield row_count, row_values


# ---------------------------------------------------------------------------
# Value coercion helpers
# ---------------------------------------------------------------------------

_BOOL_TRUE = {"是", "1", "true", "True", "TRUE", "yes", "Y", "y"}
_BOOL_FALSE = {"否", "0", "false", "False", "FALSE", "no", "N", "n", ""}


def _coerce_bool(value: Any) -> Optional[bool]:
    """中文 '否/是' / '0/1' / 'true/false' → bool. Returns None when unrecognizable."""
    if value is None:
        return None
    s = str(value).strip()
    if s in _BOOL_TRUE:
        return True
    if s in _BOOL_FALSE:
        return False
    return None


def _split_array(value: Any) -> List[str]:
    """Split a delimited string ('爆款,新品' / 'x;y') into a unique-preserving list."""
    if value is None:
        return []
    raw = str(value).strip()
    if not raw:
        return []
    parts = [p.strip() for p in raw.replace(";", ",").replace("；", ",").replace("、", ",").split(",")]
    out: List[str] = []
    seen: set[str] = set()
    for p in parts:
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    return out


# ---------------------------------------------------------------------------
# Header inspection (Stage 1 — UI shows mapping preview)
# ---------------------------------------------------------------------------


@dataclass
class InspectResult:
    """Result of header-only inspection."""

    sheet_name: str
    total_cols: int
    headers: List[str]
    auto_mapping: Dict[int, str] = field(default_factory=dict)
    unmatched_col_idx: List[int] = field(default_factory=list)
    missing_required: List[str] = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        # 首选中文名 = CANDIDATE_NAMES[target][0]; 让前端 Select 显示 "中文 · english_key"
        target_labels = {
            target: (names[0] if names else target)
            for target, names in CANDIDATE_NAMES.items()
        }
        return {
            "sheet_name": self.sheet_name,
            "total_cols": self.total_cols,
            "headers": self.headers,
            "auto_mapping": {str(k): v for k, v in self.auto_mapping.items()},
            "unmatched_col_idx": self.unmatched_col_idx,
            "missing_required": self.missing_required,
            "candidate_names": CANDIDATE_NAMES,
            "target_labels": target_labels,
            "required_targets": sorted(REQUIRED_TARGETS),
            "physical_targets": sorted(PHYSICAL_COLUMN_TARGETS),
            "metadata_targets": sorted(METADATA_ERP_FIELDS),
            "image_targets": sorted(IMAGE_FIELDS),
            "dimension_targets": sorted(DIMENSION_FIELDS),
            "error": self.error,
        }


def inspect_xlsx(file_bytes: bytes) -> InspectResult:
    """Stage 1 — read only the header row, return identified mapping.

    Does NOT touch the DB and does NOT iterate data rows; cheap (<100ms even
    for the 950 MB file because we stop after the first ``<row>`` element).
    """
    headers: List[str] = []
    auto_mapping: Dict[int, str] = {}

    # Pre-build "candidate name → target field" reverse index for O(1) lookup
    name_to_target: Dict[str, str] = {}
    for target, names in CANDIDATE_NAMES.items():
        for n in names:
            name_to_target.setdefault(_norm_str(n) or "", target)

    try:
        for row_idx, values in _iter_rows(file_bytes):
            headers = [_norm_str(v) or "" for v in values]
            for col_idx, header in enumerate(headers):
                if not header:
                    continue
                target = name_to_target.get(header)
                if target is not None:
                    auto_mapping[col_idx] = target
            break  # header only
    except Exception as exc:  # noqa: BLE001
        return InspectResult(
            sheet_name="sheetTitle",
            total_cols=0,
            headers=[],
            error=f"Failed to parse XLSX header: {exc}",
        )

    unmatched = [i for i, h in enumerate(headers) if h and i not in auto_mapping]
    mapped_targets = set(auto_mapping.values())
    missing_required = [t for t in REQUIRED_TARGETS if t not in mapped_targets]

    return InspectResult(
        sheet_name="sheetTitle",
        total_cols=len(headers),
        headers=headers,
        auto_mapping=auto_mapping,
        unmatched_col_idx=unmatched,
        missing_required=missing_required,
    )


# ---------------------------------------------------------------------------
# Row payload construction (Stage 2/3 shared)
# ---------------------------------------------------------------------------


@dataclass
class RowPayload:
    """Parsed payload for one Excel row, before DB upsert."""

    erp_sku_barcode: str
    physical: Dict[str, Any] = field(default_factory=dict)
    metadata_erp: Dict[str, Any] = field(default_factory=dict)
    images: Dict[str, str] = field(default_factory=dict)
    dimensions: Dict[str, str] = field(default_factory=dict)
    raw_errors: List[str] = field(default_factory=list)


def _parse_row(
    row_values: List[str],
    mapping: Dict[int, str],
) -> Optional[RowPayload]:
    """Convert a single row's raw cells into a typed ``RowPayload``.

    Returns ``None`` when the row has no usable barcode (caller treats as skip).
    """
    field_to_raw: Dict[str, str] = {}
    for col_idx, target in mapping.items():
        if col_idx >= len(row_values):
            continue
        val = row_values[col_idx]
        if val == "":
            continue
        field_to_raw[target] = val

    barcode = _norm_str(field_to_raw.get("erp_sku_barcode"))
    if not barcode:
        return None

    payload = RowPayload(erp_sku_barcode=barcode)

    for target, raw_val in field_to_raw.items():
        if target == "erp_sku_barcode":
            continue
        if target in PHYSICAL_COLUMN_TARGETS:
            if target in ("is_blocked", "is_deleted_at_source"):
                b = _coerce_bool(raw_val)
                if b is not None:
                    payload.physical[target] = b
            elif target == "source_updated_at":
                dt = _parse_excel_datetime(raw_val)
                if dt is not None:
                    payload.physical[target] = dt
            else:
                v = _norm_str(raw_val)
                if v is not None:
                    payload.physical[target] = v
        elif target in IMAGE_FIELDS:
            v = _norm_str(raw_val)
            if v is not None:
                payload.images[IMAGE_FIELDS[target]] = v
        elif target in DIMENSION_FIELDS:
            v = _norm_str(raw_val)
            if v is not None:
                payload.dimensions[DIMENSION_FIELDS[target]] = v
        elif target in METADATA_ERP_FIELDS:
            if target in ARRAY_FIELDS:
                arr = _split_array(raw_val)
                if arr:
                    payload.metadata_erp[target] = arr
            elif target == "created_at_at_source":
                dt = _parse_excel_datetime(raw_val)
                if dt is not None:
                    payload.metadata_erp["created_at"] = dt.isoformat()
            else:
                v = _norm_str(raw_val)
                if v is not None:
                    payload.metadata_erp[target] = v

    return payload


# ---------------------------------------------------------------------------
# Diff / report
# ---------------------------------------------------------------------------


@dataclass
class DryRunReport:
    """Result of dry-run (or commit) — never raises on per-row errors."""

    mode: str  # "dry_run" or "commit"
    total_rows: int = 0
    parsed_rows: int = 0
    new_rows: int = 0
    updated_rows: int = 0
    fields_changed: int = 0
    skipped_no_barcode: int = 0
    duplicate_in_file: int = 0
    sample_changes: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[Dict[str, Any]] = field(default_factory=list)
    elapsed_seconds: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mode": self.mode,
            "total_rows": self.total_rows,
            "parsed_rows": self.parsed_rows,
            "new_rows": self.new_rows,
            "updated_rows": self.updated_rows,
            "fields_changed": self.fields_changed,
            "skipped_no_barcode": self.skipped_no_barcode,
            "duplicate_in_file": self.duplicate_in_file,
            "sample_changes": self.sample_changes,
            "errors": self.errors[:50],
            "elapsed_seconds": round(self.elapsed_seconds, 2),
        }


def apply_payload_to_row(
    row_obj: models.SkuMaster,
    payload: RowPayload,
    *,
    is_new: bool,
    requested_by: Optional[str],
    source: str = "jackyun_erp_goods_xlsx",
) -> int:
    """Apply ``payload`` to ``row_obj`` with **narrow overwrite** semantics.

    Only fields present in ``payload`` are touched. Fields not in payload
    (e.g. ``production_process`` when not in mapping) are left intact.

    ``source`` is recorded in ``metadata.source`` on new rows for audit.
    Callers from the API sync path should pass ``"jackyun_erp_goods_api"``
    so dead-letter triage can distinguish Excel imports from API syncs.

    Returns the number of fields actually changed (for the diff report).

    PUBLIC API — also imported by ``integrations.jackyun.mappers.goods`` for
    the daily API sync line. Keep the signature backward compatible.
    """
    changed = 0

    for col, val in payload.physical.items():
        if getattr(row_obj, col, None) != val:
            setattr(row_obj, col, val)
            changed += 1

    if payload.images:
        cur_images = dict(row_obj.images_json or {})
        for k, v in payload.images.items():
            if cur_images.get(k) != v:
                cur_images[k] = v
                changed += 1
        row_obj.images_json = cur_images

    if payload.metadata_erp or payload.dimensions or is_new:
        meta = dict(row_obj.metadata_json or {})
        erp_meta = dict(meta.get("erp") or {})
        for k, v in payload.metadata_erp.items():
            if erp_meta.get(k) != v:
                erp_meta[k] = v
                changed += 1
        if payload.dimensions:
            dims = dict(erp_meta.get("dims") or {})
            for k, v in payload.dimensions.items():
                if dims.get(k) != v:
                    dims[k] = v
                    changed += 1
            erp_meta["dims"] = dims
        if erp_meta:
            erp_meta.setdefault("imported_at", _utcnow().isoformat())
            erp_meta.setdefault("imported_by", requested_by)
            meta["erp"] = erp_meta
        if is_new:
            meta.setdefault("source", source)
            meta.setdefault("imported_by", requested_by)
        row_obj.metadata_json = meta

    return changed


# Backward compatibility shim: keep the underscored alias so existing
# callers in this module (and any external imports we missed) keep working.
_apply_payload_to_row = apply_payload_to_row


def _execute(
    db: Session,
    *,
    file_bytes: bytes,
    mapping: Dict[int, str],
    requested_by: Optional[str],
    commit: bool,
    batch_size: int = 5000,
    sample_limit: int = 5,
) -> DryRunReport:
    """Shared workhorse for both dry_run and commit. Single streaming pass."""
    report = DryRunReport(mode="commit" if commit else "dry_run")
    t0 = datetime.now()

    seen_barcodes: set[str] = set()
    batch_count = 0

    for row_idx, row_values in _iter_rows(file_bytes):
        if row_idx == 1:
            continue  # header
        report.total_rows += 1

        try:
            payload = _parse_row(row_values, mapping)
        except Exception as exc:  # noqa: BLE001
            report.errors.append({"row": row_idx, "error": str(exc)})
            continue

        if payload is None:
            report.skipped_no_barcode += 1
            continue

        if payload.erp_sku_barcode in seen_barcodes:
            report.duplicate_in_file += 1
            continue
        seen_barcodes.add(payload.erp_sku_barcode)
        report.parsed_rows += 1

        # Lookup existing row
        existing = (
            db.query(models.SkuMaster)
            .filter(
                models.SkuMaster.erp_sku_barcode == payload.erp_sku_barcode,
                models.SkuMaster.is_archived.is_(False),
            )
            .first()
        )

        if existing is None:
            row_obj = models.SkuMaster(
                erp_sku_barcode=payload.erp_sku_barcode,
                metadata_json={},
                images_json={},
            )
            changes = _apply_payload_to_row(row_obj, payload, is_new=True, requested_by=requested_by)
            if commit:
                db.add(row_obj)
            report.new_rows += 1
            report.fields_changed += max(changes, 1)  # creation counts as ≥1 change
            if len(report.sample_changes) < sample_limit:
                report.sample_changes.append(
                    {
                        "row": row_idx,
                        "barcode": payload.erp_sku_barcode,
                        "action": "new",
                        "physical": {k: _stringify(v) for k, v in payload.physical.items()},
                        "metadata_erp_keys": list(payload.metadata_erp.keys()),
                    }
                )
        else:
            changes = _apply_payload_to_row(existing, payload, is_new=False, requested_by=requested_by)
            if changes > 0:
                report.updated_rows += 1
                report.fields_changed += changes
                if len(report.sample_changes) < sample_limit:
                    report.sample_changes.append(
                        {
                            "row": row_idx,
                            "barcode": payload.erp_sku_barcode,
                            "action": "update",
                            "fields_changed": changes,
                            "physical": {k: _stringify(v) for k, v in payload.physical.items()},
                        }
                    )

        batch_count += 1
        if commit and batch_count >= batch_size:
            db.commit()
            batch_count = 0

    if commit and batch_count > 0:
        db.commit()
    elif not commit:
        db.rollback()  # discard all SQL-side state from dry-run lookups

    report.elapsed_seconds = (datetime.now() - t0).total_seconds()
    return report


def _stringify(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def dry_run(
    db: Session,
    *,
    file_bytes: bytes,
    mapping: Dict[int, str],
    requested_by: Optional[str],
) -> Dict[str, Any]:
    """Stage 2 — full stream parse, simulate upsert, return diff report. **No DB write**."""
    report = _execute(
        db,
        file_bytes=file_bytes,
        mapping=mapping,
        requested_by=requested_by,
        commit=False,
    )
    return report.to_dict()


def import_commit(
    db: Session,
    *,
    file_bytes: bytes,
    mapping: Dict[int, str],
    requested_by: Optional[str],
    batch_size: int = 5000,
) -> Dict[str, Any]:
    """Stage 3 — actually commit in batches of ``batch_size`` rows."""
    report = _execute(
        db,
        file_bytes=file_bytes,
        mapping=mapping,
        requested_by=requested_by,
        commit=True,
        batch_size=batch_size,
    )
    return report.to_dict()

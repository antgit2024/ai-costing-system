"""Jackyun ``erp.storage.goodslist`` payload → ``sku_master`` upsert.

Reuses the **narrow-overwrite** core from
``planner.services.jackyun_goods_import_service.apply_payload_to_row``
so Excel imports and API syncs converge on identical write semantics
(only fields present in the payload are touched; unrelated fields like
``production_process`` from the local dev workflow are preserved).

Field mapping (api_record → RowPayload):

| Jackyun API field          | Our field                              | Notes                       |
|----------------------------|----------------------------------------|-----------------------------|
| skuBarcode                 | erp_sku_barcode (PK)                   | reject row if missing       |
| skuCode                    | physical.out_sku_code                  | =outSkuCode (writeback key) |
| goodsId                    | physical.erp_goods_id                  |                             |
| skuId                      | physical.erp_sku_id                    |                             |
| goodsName                  | physical.product_name                  |                             |
| goodsNo                    | physical.product_code                  |                             |
| skuName                    | physical.spec_text                     |                             |
| isBlockup OR skuIsBlockup  | physical.is_blocked                    | OR-merge (either disables)  |
| isDelete                   | physical.is_deleted_at_source          |                             |
| skuGmtModified (ms)        | physical.source_updated_at             | ms epoch → UTC datetime     |
| flagData                   | metadata.erp.sku_flag_synced (array)   |                             |
| skuNo                      | metadata.erp.spec_no                   |                             |
| cateName                   | metadata.erp.category                  |                             |
| cateFullName               | metadata.erp.category_full             |                             |
| unitName                   | metadata.erp.unit                      |                             |
| goodsMemo                  | metadata.erp.memo                      |                             |
| memo                       | metadata.erp.sku_memo                  |                             |
| mainBarcode (if exposed)   | metadata.erp.main_barcode              |                             |
| colorName                  | metadata.erp.color                     |                             |
| sizeName                   | metadata.erp.size                      |                             |
| abcCate                    | metadata.erp.abc_cate                  |                             |
| skuLength/Width/Height/Weight, volume | metadata.erp.dims.{...}     |                             |
| imgUrlList[main].imgKey    | images.product_image                   | first ``isMainImage=1``     |
| skuImgUrl                  | images.spec_image                      |                             |
| goodsAttr (int)            | metadata.erp.goods_attr                | numeric enum                |
| goodsField1..50            | metadata.erp.goods_fields[N]           | only if non-null            |
| skuField1..30              | metadata.erp.sku_fields[N]             | only if non-null            |
| gmtCreate (ms)             | metadata.erp.created_at (iso str)      |                             |

Note: ``skuCode`` is the API surface name for what the writeback line refers
to as ``outSkuCode``. Per 2026-05-16 live probe, this is 100% null for the
current tenant — populated only after we run the writeback line G1-H.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from ....planner import models
from ....planner.services.jackyun_goods_import_service import (
    RowPayload,
    apply_payload_to_row,
)


SOURCE_SYSTEM = "jackyun_erp_goods_api"


def _norm_str(v: Any) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _ms_to_utc_dt(ms: Any) -> Optional[datetime]:
    """Convert a Jackyun millisecond-epoch timestamp to a naive UTC datetime.

    Returns None on any parsing failure (caller treats as "no value").
    """
    if ms is None:
        return None
    try:
        ms_int = int(ms)
    except (TypeError, ValueError):
        return None
    if ms_int <= 0:
        return None
    try:
        return datetime.fromtimestamp(ms_int / 1000, tz=timezone.utc).replace(tzinfo=None)
    except (OverflowError, OSError, ValueError):
        return None


def _ms_to_utc_iso(ms: Any) -> Optional[str]:
    dt = _ms_to_utc_dt(ms)
    return dt.isoformat() if dt else None


def _coerce_int_bool(v: Any) -> Optional[bool]:
    """Jackyun ``isXxx`` fields are int 0/1; treat anything else as None."""
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, int):
        return bool(v)
    if isinstance(v, str):
        s = v.strip()
        if s in ("0", "false", "False"):
            return False
        if s in ("1", "true", "True"):
            return True
    return None


def _pick_main_image_url(img_url_list: Any) -> Optional[str]:
    """Pick the main image URL out of ``imgUrlList``.

    Each element is a dict with keys: ``id``, ``goodsId``, ``imgUrl`` (an
    embedded JSON-string mapping ``pic400x400/pic0x0/pic50x50``), ``isMainImage``,
    ``imagePosition``, ``imgKey`` (canonical URL string).

    Strategy:
      1. Prefer ``imgKey`` of the first item with ``isMainImage == 1``.
      2. Fallback to ``imgKey`` of the first item.
      3. Fallback to parsing ``imgUrl`` as JSON and picking pic400x400 / pic0x0.
    """
    if not isinstance(img_url_list, list) or not img_url_list:
        return None
    main_first = next(
        (it for it in img_url_list if isinstance(it, dict) and it.get("isMainImage") == 1),
        None,
    )
    candidate = main_first or img_url_list[0]
    if not isinstance(candidate, dict):
        return None
    img_key = _norm_str(candidate.get("imgKey"))
    if img_key:
        return img_key
    img_url = candidate.get("imgUrl")
    if isinstance(img_url, str) and img_url.startswith("{"):
        try:
            parsed = json.loads(img_url)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            for k in ("pic400x400", "pic0x0", "pic50x50"):
                v = _norm_str(parsed.get(k))
                if v:
                    return v
    elif isinstance(img_url, str):
        return _norm_str(img_url)
    return None


def _collect_indexed_fields(record: Dict[str, Any], prefix: str, max_n: int) -> Dict[str, Any]:
    """Collect non-null ``{prefix}{N}`` fields into a sparse mapping.

    Keys in the output use the integer N as a string (e.g. ``"5"``) so the
    JSONB stays compact. Empty result → empty dict (caller suppresses).
    """
    out: Dict[str, Any] = {}
    for n in range(1, max_n + 1):
        v = record.get(f"{prefix}{n}")
        if v is None or v == "" or v == []:
            continue
        out[str(n)] = v
    return out


def api_payload_to_row_payload(record: Dict[str, Any]) -> Optional[RowPayload]:
    """Map one ``erp.storage.goodslist`` record to a ``RowPayload``.

    Returns None when the row has no usable ``skuBarcode`` (caller skips).
    """
    barcode = _norm_str(record.get("skuBarcode"))
    if not barcode:
        return None

    payload = RowPayload(erp_sku_barcode=barcode)

    # ---- Physical columns ----
    sku_code = _norm_str(record.get("skuCode"))
    if sku_code:
        payload.physical["out_sku_code"] = sku_code
    goods_id = _norm_str(record.get("goodsId"))
    if goods_id:
        payload.physical["erp_goods_id"] = goods_id
    sku_id = _norm_str(record.get("skuId"))
    if sku_id:
        payload.physical["erp_sku_id"] = sku_id
    product_name = _norm_str(record.get("goodsName"))
    if product_name:
        payload.physical["product_name"] = product_name
    product_code = _norm_str(record.get("goodsNo"))
    if product_code:
        payload.physical["product_code"] = product_code
    spec_text = _norm_str(record.get("skuName"))
    if spec_text:
        payload.physical["spec_text"] = spec_text

    # is_blocked: OR of goods-level and sku-level (either disables the row)
    goods_blocked = _coerce_int_bool(record.get("isBlockup"))
    sku_blocked = _coerce_int_bool(record.get("skuIsBlockup"))
    if goods_blocked is not None or sku_blocked is not None:
        payload.physical["is_blocked"] = bool(goods_blocked) or bool(sku_blocked)

    is_deleted = _coerce_int_bool(record.get("isDelete"))
    if is_deleted is not None:
        payload.physical["is_deleted_at_source"] = is_deleted

    # source_updated_at: prefer skuGmtModified (per-spec change), fall back to
    # goodsGmtModified (goods-level change).
    upd_dt = _ms_to_utc_dt(record.get("skuGmtModified")) or _ms_to_utc_dt(
        record.get("goodsGmtModified")
    )
    if upd_dt:
        payload.physical["source_updated_at"] = upd_dt

    # ---- metadata.erp.* mirrors ----
    spec_no = _norm_str(record.get("skuNo"))
    if spec_no:
        payload.metadata_erp["spec_no"] = spec_no
    cate = _norm_str(record.get("cateName"))
    if cate:
        payload.metadata_erp["category"] = cate
    cate_full = _norm_str(record.get("cateFullName"))
    if cate_full:
        payload.metadata_erp["category_full"] = cate_full
    unit = _norm_str(record.get("unitName"))
    if unit:
        payload.metadata_erp["unit"] = unit
    goods_memo = _norm_str(record.get("goodsMemo"))
    if goods_memo:
        payload.metadata_erp["memo"] = goods_memo
    sku_memo = _norm_str(record.get("memo"))
    if sku_memo:
        payload.metadata_erp["sku_memo"] = sku_memo
    main_barcode = _norm_str(record.get("mainBarcode"))
    if main_barcode:
        payload.metadata_erp["main_barcode"] = main_barcode
    color = _norm_str(record.get("colorName"))
    if color:
        payload.metadata_erp["color"] = color
    size = _norm_str(record.get("sizeName"))
    if size:
        payload.metadata_erp["size"] = size
    abc_cate = _norm_str(record.get("abcCate"))
    if abc_cate:
        payload.metadata_erp["abc_cate"] = abc_cate
    goods_alias = _norm_str(record.get("goodsAlias"))
    if goods_alias:
        payload.metadata_erp["goods_alias"] = goods_alias
    brand_name = _norm_str(record.get("brandName"))
    if brand_name:
        payload.metadata_erp["brand"] = brand_name
    warehouse = _norm_str(record.get("warehouseName"))
    if warehouse:
        payload.metadata_erp["warehouse"] = warehouse
    vendor = _norm_str(record.get("defaultVendName"))
    if vendor:
        payload.metadata_erp["default_vendor"] = vendor

    # goodsAttr is a numeric enum (1=成品 / 2=半成品 / 3=原料 / ...)
    goods_attr = record.get("goodsAttr")
    if isinstance(goods_attr, int):
        payload.metadata_erp["goods_attr"] = goods_attr

    # flagData (规格标记) — multi-value; the API returns either a list of
    # strings, a list of dicts, or null. Normalize to a list of strings.
    flag_data = record.get("flagData")
    if isinstance(flag_data, list) and flag_data:
        flat: List[str] = []
        for item in flag_data:
            if isinstance(item, str):
                s = item.strip()
                if s:
                    flat.append(s)
            elif isinstance(item, dict):
                for k in ("flagName", "name", "label", "code"):
                    v = _norm_str(item.get(k))
                    if v:
                        flat.append(v)
                        break
        if flat:
            payload.metadata_erp["sku_flag_synced"] = flat

    # gmtCreate (ms) → metadata.erp.created_at (iso str, mirrors Excel path)
    created_iso = _ms_to_utc_iso(record.get("gmtCreate") or record.get("skuGmtCreate"))
    if created_iso:
        payload.metadata_erp["created_at"] = created_iso

    # Custom fields: collect non-null goodsField1..50 / skuField1..30 into
    # sparse maps under metadata.erp.goods_fields / sku_fields. Names of the
    # fields (the human Chinese labels) come from erp.goods.customfield, which
    # we'll wire up separately in the customfield-dictionary line.
    goods_fields = _collect_indexed_fields(record, "goodsField", 50)
    if goods_fields:
        payload.metadata_erp["goods_fields"] = goods_fields
    sku_fields = _collect_indexed_fields(record, "skuField", 30)
    if sku_fields:
        payload.metadata_erp["sku_fields"] = sku_fields

    # ---- Dimensions ----
    for src, dst in (
        ("skuLength", "length"),
        ("skuWidth", "width"),
        ("skuHeight", "height"),
        ("skuWeight", "weight_g"),
        ("volume", "volume"),
    ):
        v = record.get(src)
        if v is None or v == "":
            continue
        payload.dimensions[dst] = str(v)

    # ---- Images ----
    main_url = _pick_main_image_url(record.get("imgUrlList"))
    if main_url:
        payload.images["product_image"] = main_url
    spec_img = _norm_str(record.get("skuImgUrl"))
    if spec_img:
        payload.images["spec_image"] = spec_img

    return payload


def upsert_goods_from_payload(
    db: Session,
    *,
    record: Dict[str, Any],
    requested_by: str = SOURCE_SYSTEM,
) -> Tuple[int, int, int, int]:
    """Upsert a single ``erp.storage.goodslist`` record into ``sku_master``.

    Returns a 4-tuple ``(rows_total, inserted, updated, fields_changed)``:
      * ``rows_total``: 1 if the record was processed (always 1 here unless
        the record had no usable barcode, in which case the caller should
        have already filtered with the iter — but we double-check defensively
        and return all-zeros for that case).
      * ``inserted``: 1 if a new SkuMaster row was created, else 0.
      * ``updated``: 1 if an existing row had ≥1 field actually changed, else 0.
      * ``fields_changed``: total count of physical/metadata/image fields
        whose value actually differed (used by the dry-run-style report).

    Per-record errors are surfaced as exceptions for the caller (sync_jobs)
    to wrap in ``record_dead_letter`` rather than aborting the run.
    """
    payload = api_payload_to_row_payload(record)
    if payload is None:
        return 0, 0, 0, 0

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
        changes = apply_payload_to_row(
            row_obj,
            payload,
            is_new=True,
            requested_by=requested_by,
            source=SOURCE_SYSTEM,
        )
        db.add(row_obj)
        return 1, 1, 0, max(changes, 1)

    changes = apply_payload_to_row(
        existing,
        payload,
        is_new=False,
        requested_by=requested_by,
        source=SOURCE_SYSTEM,
    )
    if changes > 0:
        return 1, 0, 1, changes
    return 1, 0, 0, 0

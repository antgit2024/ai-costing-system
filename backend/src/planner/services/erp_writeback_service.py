"""ERP 反写模块 — 把本地 SkuMaster 的关键字段推送回吉客云.

两条交付路径
============

1. **Excel 模板下载** (方案 B, 立即可用)
   - 生成吉客云后台「批量修改货品」兼容的 xlsx
   - 业务在吉客云后台手工导入即可完成反写
   - 入口: ``POST /sku-master/erp-writeback/export-excel`` → ``build_writeback_excel()``

2. **异步队列 (持久化 + 未来 API 直推)** (方案 A)
   - 把反写意图落到 ``integration_writeback_jobs`` 表
   - Worker 由后续模块消费; 没有 worker 时 job 会留在 pending 状态
   - 入口: ``POST /sku-master/erp-writeback/enqueue`` → ``enqueue_writeback_jobs()``
   - 抽屉「反写历史」Tab: ``GET /sku-master/{id}/erp-writeback/history`` → ``list_jobs_for_sku()``

两条路径共享 ``WRITEBACK_FIELD_MAP`` 字段映射表 + ``extract_writeback_value()``
抽取器, 保证 Excel 列值与 job payload 值一致.

字段映射 (``WRITEBACK_FIELD_MAP``)
---------------------------------

| 内部 key                   | 吉客云 Excel 表头  | 吉客云 API 字段        | 反写源 (SkuMaster)                          |
|----------------------------|--------------------|------------------------|---------------------------------------------|
| spec_text                  | 规格               | skuName                | row.spec_text                               |
| model_code_reg             | 模型编码(规)       | model_code             | row.metadata.bound_variant_code (识别结果)  |
| process_instructions_reg   | 工艺说明(规)       | process_instructions   | row.production_process                      |
| sku_flag                   | 规格标记           | flagData               | row.metadata.erp.sku_flag (本地真源, 逗号分隔) |

主键列「条码」(skuBarcode) = ``row.erp_sku_barcode`` 始终是 Excel 第一列.
"""

from __future__ import annotations

import io
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple
from uuid import uuid4

from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models


SOURCE_SYSTEM = "jackyun"
TARGET_TYPE = "sku_master"
DEFAULT_API_METHOD = "erp.storage.goods.update"  # 占位 (worker 尚未上线)


# ---------------------------------------------------------------------------
# 字段映射定义
# ---------------------------------------------------------------------------


def _extract_spec_text(row: "models.SkuMaster") -> Optional[str]:
    s = getattr(row, "spec_text", None)
    return s.strip() if isinstance(s, str) and s.strip() else None


def _extract_model_code_reg(row: "models.SkuMaster") -> Optional[str]:
    # 业务定义: "模型编码(规)" 反写的是已绑定的变体码 (如 KB8-001 / OZU-001),
    # 而不是模型短码 (KB8). 见 2026-05 用户澄清.
    meta = getattr(row, "metadata_json", None) or {}
    v = meta.get("bound_variant_code") if isinstance(meta, dict) else None
    if isinstance(v, str) and v.strip():
        return v.strip().upper()
    # 回退: 没识别到变体但绑了模型, 也把模型码推回去, 避免反写 NULL
    bm = getattr(row, "bound_model_code", None)
    if isinstance(bm, str) and bm.strip():
        return bm.strip().upper()
    return None


def _extract_process_instructions(row: "models.SkuMaster") -> Optional[str]:
    s = getattr(row, "production_process", None)
    return s.strip() if isinstance(s, str) and s.strip() else None


def _extract_sku_flag(row: "models.SkuMaster") -> Optional[str]:
    """规格标记: 本地真源是 metadata.erp.sku_flag (list[str]).

    吉客云后台「规格标记」单元格用中文逗号分隔多值, 这里直接拼成 string,
    让运营能直接复制到吉客云后台.
    """
    meta = getattr(row, "metadata_json", None) or {}
    if not isinstance(meta, dict):
        return None
    erp = meta.get("erp") if isinstance(meta.get("erp"), dict) else {}
    tags = erp.get("sku_flag") if isinstance(erp, dict) else None
    if not isinstance(tags, list) or not tags:
        return None
    flat = [str(t).strip() for t in tags if str(t).strip()]
    return "，".join(flat) if flat else None


# 内部 key → (Excel 中文表头, 吉客云 API 字段名, 抽取器)
WRITEBACK_FIELD_MAP: Dict[str, Tuple[str, str, Callable[["models.SkuMaster"], Any]]] = {
    "spec_text": ("规格", "skuName", _extract_spec_text),
    "model_code_reg": ("模型编码(规)", "model_code", _extract_model_code_reg),
    "process_instructions_reg": ("工艺说明(规)", "process_instructions", _extract_process_instructions),
    "sku_flag": ("规格标记", "flagData", _extract_sku_flag),
}


ALL_WRITEBACK_FIELDS = list(WRITEBACK_FIELD_MAP.keys())


def normalize_field_list(fields: Optional[List[str]]) -> List[str]:
    """把入参的 fields 收敛到合法 + 去重 + 保持 WRITEBACK_FIELD_MAP 的顺序."""
    if not fields:
        return list(ALL_WRITEBACK_FIELDS)
    requested = {str(f).strip() for f in fields if str(f).strip()}
    return [f for f in ALL_WRITEBACK_FIELDS if f in requested]


def extract_writeback_value(row: "models.SkuMaster", field_key: str) -> Any:
    spec = WRITEBACK_FIELD_MAP.get(field_key)
    if not spec:
        return None
    _, _, extractor = spec
    try:
        return extractor(row)
    except Exception:  # noqa: BLE001 - 防御: 单字段抽取失败不应整批崩
        return None


def extract_writeback_payload(row: "models.SkuMaster", fields: List[str]) -> Dict[str, Any]:
    """生成 API 风格 payload (字段名走吉客云 API 名), 用于队列 job."""
    out: Dict[str, Any] = {}
    for f in fields:
        spec = WRITEBACK_FIELD_MAP.get(f)
        if not spec:
            continue
        _, api_name, extractor = spec
        try:
            out[api_name] = extractor(row)
        except Exception:  # noqa: BLE001
            out[api_name] = None
    return out


# ---------------------------------------------------------------------------
# 路径 1: Excel 模板下载 (方案 B)
# ---------------------------------------------------------------------------


def _resolve_rows_by_ids(db: Session, sku_master_ids: List[str]) -> List["models.SkuMaster"]:
    ids = [str(i).strip() for i in (sku_master_ids or []) if str(i).strip()]
    if not ids:
        return []
    rows = (
        db.query(models.SkuMaster)
        .filter(models.SkuMaster.id.in_(ids), models.SkuMaster.is_archived.is_(False))
        .all()
    )
    # 按入参顺序回排, 让 Excel 行顺序符合用户预期
    by_id: Dict[str, models.SkuMaster] = {str(r.id): r for r in rows}
    return [by_id[i] for i in ids if i in by_id]


def build_writeback_excel(
    db: Session,
    *,
    sku_master_ids: List[str],
    fields: Optional[List[str]] = None,
) -> Tuple[bytes, Dict[str, Any]]:
    """生成吉客云「批量修改货品」兼容的 xlsx.

    Returns: ``(xlsx_bytes, summary)``
        summary = {
            "total_rows": int,
            "fields": [internal_key, ...],
            "skipped_missing_barcode": int,
            "filename": str,
        }

    Excel 结构 (Sheet1 = 数据, Sheet2 = 字段映射文档):
        Sheet1 列 = [条码, 外部编码, 货品编号, 货品名称] + 用户选中的反写字段中文表头
        - 条码  ← row.erp_sku_barcode (主键, 必填; 缺失行会被跳过)
        - 外部编码 ← row.out_sku_code (已反写过的会有, 仅供运营核对)
        - 货品编号 / 货品名称 仅供运营在 Excel 里识别行, 吉客云导入时只用「条码」
        - 反写字段列只输出有值的内容 (空值留空, 吉客云不会覆盖)
    """
    from openpyxl import Workbook  # 局部 import, 避免 cold path 进程占用

    fields = normalize_field_list(fields)
    rows = _resolve_rows_by_ids(db, sku_master_ids)

    wb = Workbook(write_only=True)

    # ---- Sheet1: 数据 ----
    ws = wb.create_sheet("批量修改货品")
    base_headers = ["条码", "外部编码", "货品编号", "货品名称"]
    field_headers = [WRITEBACK_FIELD_MAP[f][0] for f in fields]
    ws.append(base_headers + field_headers)

    skipped = 0
    written = 0
    for r in rows:
        barcode = (getattr(r, "erp_sku_barcode", None) or "").strip()
        if not barcode:
            skipped += 1
            continue
        out_sku_code = (getattr(r, "out_sku_code", None) or "")
        product_code = (getattr(r, "product_code", None) or "")
        product_name = (getattr(r, "product_name", None) or "")
        line = [barcode, out_sku_code, product_code, product_name]
        for f in fields:
            v = extract_writeback_value(r, f)
            line.append("" if v in (None, "") else str(v))
        ws.append(line)
        written += 1

    # ---- Sheet2: 字段映射文档 (帮助运营理解列含义) ----
    ws2 = wb.create_sheet("字段映射说明")
    ws2.append(["内部字段", "吉客云 Excel 表头", "吉客云 API 字段", "说明"])
    notes = {
        "spec_text": "网店「规格」/ skuName, 商品档案的属性规格文字",
        "model_code_reg": "吉客云「模型编码(规)」, 推送的是识别后的变体码 (KB8-001)",
        "process_instructions_reg": "吉客云「工艺说明(规)」, 推送的是本地维护的生产工艺",
        "sku_flag": "规格标记, 多值用中文逗号 ， 分隔",
    }
    for f, (hdr, api, _) in WRITEBACK_FIELD_MAP.items():
        ws2.append([f, hdr, api, notes.get(f, "")])

    bio = io.BytesIO()
    wb.save(bio)
    bio.seek(0)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"jackyun_writeback_{ts}.xlsx"
    summary = {
        "total_rows": written,
        "fields": fields,
        "skipped_missing_barcode": skipped,
        "filename": filename,
    }
    return bio.getvalue(), summary


# ---------------------------------------------------------------------------
# 路径 2: 异步队列 (方案 A)
# ---------------------------------------------------------------------------


def _now_naive_utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def enqueue_writeback_jobs(
    db: Session,
    *,
    sku_master_ids: List[str],
    fields: Optional[List[str]] = None,
    requested_by: Optional[str] = None,
    api_method: str = DEFAULT_API_METHOD,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """把反写意图入队到 ``integration_writeback_jobs``.

    每条 (sku, ) 生成一个 job, payload 携带本次反写的 4 字段子集.
    worker 由后续模块实现; 当前 enqueue 后 job 留在 ``status=pending``,
    业务可在抽屉「反写历史」Tab 看到 job 状态.

    幂等性: 同一 sku 在 status in {pending, retrying} 的旧 job 会被合并/取消,
    避免运营重复点出现一堆并发任务.
    """
    fields = normalize_field_list(fields)
    rows = _resolve_rows_by_ids(db, sku_master_ids)

    enqueued: List[Dict[str, Any]] = []
    superseded: List[str] = []
    skipped: List[Dict[str, Any]] = []
    now = _now_naive_utc()

    for r in rows:
        barcode = (getattr(r, "erp_sku_barcode", None) or "").strip()
        if not barcode:
            skipped.append({"sku_master_id": str(r.id), "reason": "missing_barcode"})
            continue
        payload = extract_writeback_payload(r, fields)
        # 至少要有一个反写字段非空, 否则没意义
        if not any(v not in (None, "") for v in payload.values()):
            skipped.append({"sku_master_id": str(r.id), "reason": "no_value_to_writeback"})
            continue

        # 旧的同 sku pending 任务合并: 标记为 superseded, 留审计
        if not dry_run:
            stale = (
                db.query(models.IntegrationWritebackJob)
                .filter(
                    models.IntegrationWritebackJob.source_system == SOURCE_SYSTEM,
                    models.IntegrationWritebackJob.target_type == TARGET_TYPE,
                    models.IntegrationWritebackJob.target_id == barcode,
                    models.IntegrationWritebackJob.status.in_(("pending", "retrying")),
                )
                .all()
            )
            for s in stale:
                s.status = "superseded"
                s.last_error = "superseded by newer enqueue"
                s.updated_at = now
                superseded.append(str(s.id))

        job_id = str(uuid4())
        job = models.IntegrationWritebackJob(
            id=job_id,
            source_system=SOURCE_SYSTEM,
            api_method=api_method,
            target_type=TARGET_TYPE,
            target_id=barcode,
            payload_json={
                "sku_master_id": str(r.id),
                "fields": fields,
                "values": payload,
            },
            status="pending",
            attempt=0,
            max_attempts=5,
            next_run_at=now,
            requested_by=requested_by,
            metadata_json={
                "product_code": getattr(r, "product_code", None),
                "product_name": getattr(r, "product_name", None),
                "out_sku_code": getattr(r, "out_sku_code", None),
            },
        )
        if not dry_run:
            db.add(job)
        enqueued.append(
            {
                "job_id": job_id,
                "sku_master_id": str(r.id),
                "erp_sku_barcode": barcode,
                "fields": fields,
                "values": payload,
            }
        )

    if not dry_run:
        db.commit()

    return {
        "enqueued_count": len(enqueued),
        "superseded_count": len(superseded),
        "skipped_count": len(skipped),
        "jobs": enqueued,
        "superseded_job_ids": superseded,
        "skipped": skipped,
        "dry_run": bool(dry_run),
    }


def list_jobs_for_sku(
    db: Session,
    *,
    sku_master_id: str,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """列出某个 sku 的反写历史 (用于抽屉「反写历史」Tab)."""
    row = db.get(models.SkuMaster, sku_master_id)
    if not row:
        return []
    barcode = (getattr(row, "erp_sku_barcode", None) or "").strip()
    if not barcode:
        return []
    q = (
        db.query(models.IntegrationWritebackJob)
        .filter(
            models.IntegrationWritebackJob.source_system == SOURCE_SYSTEM,
            models.IntegrationWritebackJob.target_type == TARGET_TYPE,
            models.IntegrationWritebackJob.target_id == barcode,
        )
        .order_by(models.IntegrationWritebackJob.created_at.desc())
        .limit(max(1, min(int(limit or 50), 200)))
    )
    out: List[Dict[str, Any]] = []
    for j in q.all():
        out.append(
            {
                "id": str(j.id),
                "source_system": j.source_system,
                "api_method": j.api_method,
                "target_id": j.target_id,
                "status": j.status,
                "attempt": int(j.attempt or 0),
                "max_attempts": int(j.max_attempts or 0),
                "next_run_at": j.next_run_at.isoformat() if j.next_run_at else None,
                "last_attempt_at": j.last_attempt_at.isoformat() if j.last_attempt_at else None,
                "last_error": j.last_error,
                "requested_by": j.requested_by,
                "payload": j.payload_json or {},
                "metadata": j.metadata_json or {},
                "created_at": j.created_at.isoformat() if j.created_at else None,
                "updated_at": j.updated_at.isoformat() if j.updated_at else None,
            }
        )
    return out


# ---------------------------------------------------------------------------
# 全局队列查看 (供 UI 「反写队列」入口)
# ---------------------------------------------------------------------------


def list_writeback_jobs(
    db: Session,
    *,
    status: Optional[str] = None,
    search: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
) -> Dict[str, Any]:
    """全局列出 integration_writeback_jobs (jackyun / sku_master).

    - ``status``: 过滤 status (pending/retrying/succeeded/failed/superseded), 多个用逗号
    - ``search``: 模糊匹配 target_id (= erp_sku_barcode), metadata.product_code,
      metadata.product_name, metadata.out_sku_code 任一
    - 默认按 created_at desc, 分页
    """
    q = db.query(models.IntegrationWritebackJob).filter(
        models.IntegrationWritebackJob.source_system == SOURCE_SYSTEM,
        models.IntegrationWritebackJob.target_type == TARGET_TYPE,
    )
    if status:
        statuses = [s.strip().lower() for s in str(status).split(",") if s.strip()]
        if statuses:
            q = q.filter(models.IntegrationWritebackJob.status.in_(statuses))
    if search:
        s = f"%{str(search).strip()}%"
        # SQL JSON 模糊匹配在 MySQL/PostgreSQL 上语法差异大, 用 cast(json -> text) 折中.
        # 性能不重要 (反写队列规模一般 <10w), 简单 OR 即可.
        from sqlalchemy import cast, String as SAString
        q = q.filter(
            models.IntegrationWritebackJob.target_id.ilike(s)
            | cast(models.IntegrationWritebackJob.metadata_json, SAString).ilike(s)
        )

    total = q.count()
    p = max(int(page or 1), 1)
    ps = max(min(int(page_size or 50), 200), 1)
    rows = (
        q.order_by(models.IntegrationWritebackJob.created_at.desc())
        .offset((p - 1) * ps)
        .limit(ps)
        .all()
    )

    items: List[Dict[str, Any]] = []
    for j in rows:
        payload = j.payload_json or {}
        meta = j.metadata_json or {}
        items.append(
            {
                "id": str(j.id),
                "source_system": j.source_system,
                "api_method": j.api_method,
                "target_id": j.target_id,
                "sku_master_id": payload.get("sku_master_id"),
                "fields": payload.get("fields") or [],
                "values": payload.get("values") or {},
                "product_code": meta.get("product_code"),
                "product_name": meta.get("product_name"),
                "out_sku_code": meta.get("out_sku_code"),
                "status": j.status,
                "attempt": int(j.attempt or 0),
                "max_attempts": int(j.max_attempts or 0),
                "next_run_at": j.next_run_at.isoformat() if j.next_run_at else None,
                "last_attempt_at": j.last_attempt_at.isoformat() if j.last_attempt_at else None,
                "last_error": j.last_error,
                "requested_by": j.requested_by,
                "created_at": j.created_at.isoformat() if j.created_at else None,
                "updated_at": j.updated_at.isoformat() if j.updated_at else None,
            }
        )

    # 顺手返回 status 维度的累计 (UI 顶部展示 "pending X / failed Y / done Z")
    status_counts_q = (
        db.query(
            models.IntegrationWritebackJob.status,
            func.count(models.IntegrationWritebackJob.id),
        )
        .filter(
            models.IntegrationWritebackJob.source_system == SOURCE_SYSTEM,
            models.IntegrationWritebackJob.target_type == TARGET_TYPE,
        )
        .group_by(models.IntegrationWritebackJob.status)
        .all()
    )
    status_counts = {str(k): int(v) for k, v in status_counts_q}

    return {
        "total": int(total),
        "page": p,
        "page_size": ps,
        "items": items,
        "status_counts": status_counts,
    }


# ---------------------------------------------------------------------------
# Worker 钩子 (供后续模块实现真正的 push)
# ---------------------------------------------------------------------------


def mark_job_done(
    db: Session,
    *,
    job_id: str,
    requested_by: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    job = db.get(models.IntegrationWritebackJob, job_id)
    if not job:
        return None
    job.status = "succeeded"
    job.last_attempt_at = _now_naive_utc()
    job.last_error = None
    job.updated_at = _now_naive_utc()
    db.commit()
    return {"id": str(job.id), "status": job.status}


def mark_job_failed(
    db: Session,
    *,
    job_id: str,
    error: str,
    retry: bool = True,
) -> Optional[Dict[str, Any]]:
    job = db.get(models.IntegrationWritebackJob, job_id)
    if not job:
        return None
    job.attempt = int(job.attempt or 0) + 1
    job.last_attempt_at = _now_naive_utc()
    job.last_error = (error or "")[:4000]
    if retry and job.attempt < int(job.max_attempts or 5):
        job.status = "retrying"
    else:
        job.status = "failed"
    job.updated_at = _now_naive_utc()
    db.commit()
    return {"id": str(job.id), "status": job.status, "attempt": job.attempt}

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

# 吉客云反写接口分流 (2026-05-17 经官方 schema dump + 实测确认):
# - "规格标记" 走 batchupdateflagbyskubarcode (轻量, biz=[{skuBarcode,flagDataName}])
# - "规格/模型编码/工艺说明" 走 skuimportbatch (UPSERT, 必须先有 outSkuCode 锚定)
#
# 早期版本默认走 erp.goods.update, 但官方 schema 103 字段里没有任何 skuList/skuField*,
# 它是 goods 维度接口, 对 sku 字段会静默忽略 (返回"成功"但实际没改). 不再使用.
# 详见 backend/scripts/probe_erp_goods_update.py + NOTES_jackyun_writeback.md
API_BATCH_UPDATE_FLAG = "erp-goods.goods.batchupdateflagbyskubarcode"
API_SKU_IMPORT_BATCH = "erp.goods.skuimportbatch"
DEFAULT_API_METHOD = API_SKU_IMPORT_BATCH  # job.api_method 默认值, 实际推送时按字段分流


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


def _extract_sku_flag(row: "models.SkuMaster") -> Any:
    """规格标记: 本地真源是 metadata.erp.sku_flag (list[str]).

    - Excel 反写: 用中文逗号 join 成 string (运营能直接复制到吉客云后台单元格)
    - API 反写 (erp.goods.update): 走 _extract_sku_flag_for_api, 见下方
    本函数保留 string 输出, 是为了向后兼容 Excel 路径; API 路径独立的抽取器.
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


# ---------- 吉客云自定义字段字典 (2026-05-17 经 erp.goods.customfield 实测拿到) ----------
# fieldName → fieldCaption (visible=1 的 8 个 sku 自定义字段)
# 用户后台没有"规格标记"自定义字段 — 规格标记走 flagData 标准字段 (list[str])
# 改这个字典或重新跑 erp.goods.customfield 即可同步最新映射.
JACKYUN_SKU_CUSTOM_FIELD_DICT: Dict[str, str] = {
    "skuField1": "模型编码",
    "skuField2": "工艺编码",
    "skuField3": "适用模型",
    "skuField4": "排版损耗",
    "skuField5": "生产损耗",
    "skuField6": "入库换算",
    "skuField7": "进货价格",
    "skuField8": "工艺说明",
}

# 内部 key → (Excel 中文表头, 吉客云 API 字段名, 抽取器)
# - "模型编码(规)" 反写到 sku 自定义字段 skuField1 (= 模型编码)
# - "工艺说明(规)" 反写到 sku 自定义字段 skuField8 (= 工艺说明)
# - "规格"      反写到标准字段 skuName
# - "规格标记"  反写到标准字段 flagData
# API 字段名前都没有 reg 后缀, 因为 ERP 那边字段名就叫"模型编码 / 工艺说明",
# 我们内部加的 "(规)" 后缀只是区分这是 sku 规格级而不是 goods 货品级.
WRITEBACK_FIELD_MAP: Dict[str, Tuple[str, str, Callable[["models.SkuMaster"], Any]]] = {
    "spec_text": ("规格", "skuName", _extract_spec_text),
    "model_code_reg": ("模型编码(规)", "skuField1", _extract_model_code_reg),
    "process_instructions_reg": ("工艺说明(规)", "skuField8", _extract_process_instructions),
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
# Cold-start 工具: 生成「补 outSkuCode」Excel
# ---------------------------------------------------------------------------
#
# 背景: erp.goods.skuimportbatch 是 UPSERT 接口, 但匹配键必须是 outSkuCode.
# 当前商家的 sku 大多数 out_sku_code 为 null (吉客云后台没填), 因此 API
# 反写整条路径走不通. 一次性解决方案: 用这个工具导出"补码 Excel", 运营拿到
# 吉客云后台「货品资料 → 导入」即可批量给所有 sku 锚定 outSkuCode = skuBarcode,
# 之后 API 反写就能跑了.


def build_outsku_code_fill_excel(
    db: Session,
    *,
    sku_master_ids: Optional[List[str]] = None,
    only_empty: bool = True,
) -> Tuple[bytes, Dict[str, Any]]:
    """生成「批量补 outSkuCode」Excel (吉客云后台导入用).

    - 默认只导出 out_sku_code 为空的 sku (only_empty=True)
    - sku_master_ids 为空时导出全量 (受 only_empty 过滤)
    - 用 skuBarcode 当 outSkuCode (一一对应, 无脑稳定)

    Excel 列:
      条码 / 货品编号 / 货品名称 / 规格名称 / 外部编码(=条码, 待补)
    运营在吉客云「货品资料 → Excel 导入 → 更新已有货品」一次跑完即可.
    """
    from openpyxl import Workbook

    q = db.query(models.SkuMaster)
    if sku_master_ids:
        q = q.filter(models.SkuMaster.id.in_(sku_master_ids))
    if only_empty:
        q = q.filter(
            (models.SkuMaster.out_sku_code.is_(None))
            | (func.length(func.trim(models.SkuMaster.out_sku_code)) == 0)
        )
    q = q.filter(
        models.SkuMaster.erp_sku_barcode.isnot(None),
        func.length(func.trim(models.SkuMaster.erp_sku_barcode)) > 0,
    ).order_by(models.SkuMaster.product_code, models.SkuMaster.erp_sku_barcode)

    wb = Workbook(write_only=True)
    ws = wb.create_sheet("补外部编码")
    ws.append(["条码", "货品编号", "货品名称", "规格名称", "外部编码"])

    written = 0
    for r in q.all():
        barcode = (getattr(r, "erp_sku_barcode", None) or "").strip()
        if not barcode:
            continue
        ws.append([
            barcode,
            getattr(r, "product_code", None) or "",
            getattr(r, "product_name", None) or "",
            getattr(r, "spec_text", None) or "",
            barcode,  # 外部编码 = 条码 (推荐, 一一对应)
        ])
        written += 1

    # Sheet2: 操作指引
    ws2 = wb.create_sheet("使用说明")
    ws2.append(["步骤", "说明"])
    for i, txt in enumerate([
        "本表用于一次性给吉客云所有 sku 锚定「外部编码 (outSkuCode)」",
        "锚定后 ERP 反写接口 (erp.goods.skuimportbatch) 才能 UPDATE 现有 sku",
        "操作: 吉客云后台 → 货品资料 → Excel 导入 → 选「更新已有货品」 → 上传本文件",
        "外部编码 = 条码 (推荐, 一一对应, 后续我方系统能自动同步回来)",
        "完成后通知技术: 系统下次同步会自动把 outSkuCode 同步到本地 sku_master",
        "之后所有反写任务 (规格 / 模型编码 / 工艺说明) 都能 API 直推",
    ], 1):
        ws2.append([str(i), txt])

    bio = io.BytesIO()
    wb.save(bio)
    bio.seek(0)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return bio.getvalue(), {
        "total_rows": written,
        "filename": f"jackyun_fill_outsku_code_{ts}.xlsx",
        "only_empty": bool(only_empty),
    }


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
# Worker 钩子 — push_one_job 真实调用吉客云
# ---------------------------------------------------------------------------


def _normalize_flag_data_name(v: Any) -> Optional[str]:
    """flagData 值规范化: list/string 都接受, 输出 batchupdateflagbyskubarcode
    要求的 ``flagDataName`` (英文逗号分隔的 string, 例: "红冲,被冲").

    吉客云会再用英文逗号 split. 上游 _extract_sku_flag 输出的是 *中文* 逗号
    分隔的 string (为兼容 Excel), 这里统一转半角.
    """
    if v is None:
        return None
    if isinstance(v, str):
        parts = [p.strip() for p in v.replace("，", ",").split(",") if p.strip()]
    elif isinstance(v, (list, tuple)):
        parts = [str(p).strip() for p in v if str(p).strip()]
    else:
        parts = [str(v).strip()] if str(v).strip() else []
    return ",".join(parts) if parts else None


def _build_flag_biz(barcode: str, flag_value: Any) -> Optional[List[Dict[str, Any]]]:
    """erp-goods.goods.batchupdateflagbyskubarcode 的 biz 构造.

    官方 schema (2026-05-17 dump):
      [{"skuBarcode": "A0001", "flagDataName": "红冲,被冲"}]
    顶层 array; flagDataName 必须是吉客云后台已存在的标记名称.
    """
    flag = _normalize_flag_data_name(flag_value)
    if not barcode or not flag:
        return None
    return [{"skuBarcode": str(barcode).strip(), "flagDataName": flag}]


def _build_skuimport_biz(
    *,
    out_sku_code: str,
    goods_no: str,
    goods_name: Optional[str],
    sku_values: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """erp.goods.skuimportbatch 的 biz 构造 (UPSERT 路径).

    匹配键 = ``outSkuCode`` (官方文档 2026-05-11 明确: 这是两个系统间的唯一锚).
    若 sku 在吉客云那边 outSkuCode 为空, **本接口无法 update**, 会走 INSERT
    并撞到现有 (goodsNo + skuName) 拒绝. 调用方必须先确保 out_sku_code 不为空.

    必填字段 (官方 schema): goodsName / goodsNo / unitName / outSkuCode
    可选传字段: skuName / skuField1..30 / goodsField1..50 / flagData / ...

    sku_values 已经按 WRITEBACK_FIELD_MAP 对齐到吉客云字段名 (skuName /
    skuField1 / skuField8 / flagData 等), 直接 spread 即可.
    """
    item: Dict[str, Any] = {
        "goodsNo": str(goods_no).strip(),
        "goodsName": str(goods_name or goods_no).strip(),
        "unitName": "件",  # 大部分商家用件; 后续如有需要可从 sku_master 取
        "outSkuCode": str(out_sku_code).strip(),
    }
    for k, v in sku_values.items():
        if v is None:
            continue
        if isinstance(v, str) and not v.strip():
            continue
        item[k] = v
    return [item]


def _row_success_check(resp_data: Any) -> Tuple[bool, Optional[str], Optional[str]]:
    """解析 jackyun response.data 数组的行级状态.

    skuimportbatch / batchupdateflagbyskubarcode 都返回:
      result.data: [{success: bool, errorMessage: str, subCode: str, outSkuCode/skuBarcode}]

    框架 sub_code 是 0030000004 "操作成功" (在 _BUSINESS_OK_SUB_CODES 白名单里), 但
    行级 success=false 时实际推送失败, 必须在这里二次校验, 否则会把失败 mark_done.

    返回: (ok, sub_code, err_msg)
    """
    if not isinstance(resp_data, list) or not resp_data:
        # data 是空 list 也算成功 (有的接口成功时返回空)
        return True, None, None
    first = resp_data[0] if isinstance(resp_data[0], dict) else {}
    ok = bool(first.get("success"))
    return ok, first.get("subCode"), first.get("errorMessage")


def _call_one_step(
    client: Any,
    *,
    api_method: str,
    biz: Any,
    db: Session,
) -> Dict[str, Any]:
    """单步调用 + 把行级 success 一并解析进来, 返回扁平 dict.

    设计目的: push_one_job 里可能要连调 2 个接口 (规格标记 + 其他字段), 每步
    结果要独立汇总. 把 IntegrationError 也内化为 dict, 调用方不再 try/except.
    """
    from src.integrations.base.errors import (
        IntegrationAuthError,
        IntegrationBusinessError,
        IntegrationTransportError,
    )

    out: Dict[str, Any] = {"api": api_method, "biz": biz}
    try:
        resp = client.call(api_method, biz, db=db)
    except IntegrationAuthError as exc:
        out.update(status="failed", retry=False, error=f"AUTH: {exc.message}",
                   biz_sub_code=exc.biz_sub_code, biz_code=exc.biz_code)
        return out
    except IntegrationBusinessError as exc:
        out.update(status="failed", retry=False, error=f"BIZ: {exc.message}",
                   biz_sub_code=exc.biz_sub_code, biz_code=exc.biz_code)
        return out
    except IntegrationTransportError as exc:
        out.update(status="retry", retry=True, error=f"NET: {exc.message}")
        return out
    except Exception as exc:  # noqa: BLE001
        out.update(status="retry", retry=True,
                   error=f"UNEXPECTED: {type(exc).__name__}: {exc}")
        return out

    # 行级二次校验 (data[0].success 决定真实成败, 框架成功 ≠ 业务成功)
    row_ok, row_sub, row_err = _row_success_check(resp.data)
    if not row_ok:
        out.update(status="failed", retry=False,
                   error=f"ROW: {row_err}" if row_err else "ROW: success=false",
                   biz_sub_code=row_sub or resp.biz_sub_code,
                   biz_code=resp.biz_code)
        return out

    out.update(status="succeeded",
               biz_sub_code=resp.biz_sub_code, biz_code=resp.biz_code)
    return out


def push_one_job(
    db: Session,
    *,
    job_id: str,
    requested_by: Optional[str] = None,
    force: bool = False,
) -> Dict[str, Any]:
    """同步推送单条 job 到吉客云 (分流到 2 个接口).

    分流规则:
      - "规格标记" (flagData) → erp-goods.goods.batchupdateflagbyskubarcode
        biz=[{skuBarcode, flagDataName}], 不依赖 outSkuCode
      - "规格 / 模型编码(规) / 工艺说明(规)" → erp.goods.skuimportbatch
        biz=[{outSkuCode 锚定, skuName, skuField1, skuField8 ...}]
        ★ 强制要求 sku.out_sku_code 不为空, 否则跳过此步并提示运营补码

    汇总规则:
      - 所有 step succeeded → mark_job_done, return "succeeded"
      - 任一 step failed 但不可重试 → mark_job_failed(retry=False)
      - 任一 step retry → mark_job_failed(retry=True), return "retrying"
      - 全部 step skipped 且原因是 needs_outsku_code → mark_job_failed(retry=False),
        return "needs_outsku_code" (UI 用这个状态展示补码引导)
    """
    from src.integrations.jackyun import build_default_client

    job = db.get(models.IntegrationWritebackJob, job_id)
    if not job:
        return {"status": "not_found", "error": f"job {job_id} 不存在"}

    if not force and job.status not in ("pending", "retrying"):
        return {
            "status": "skipped",
            "error": f"job 当前状态={job.status}, 不可推 (需 pending / retrying, 或 force=True)",
        }

    payload = job.payload_json or {}
    values: Dict[str, Any] = dict(payload.get("values") or {})
    barcode = (job.target_id or "").strip()
    if not barcode:
        mark_job_failed(db, job_id=job_id, error="missing target_id (skuBarcode 为空)", retry=False)
        return {"status": "failed", "error": "missing target_id (skuBarcode)"}

    if not values:
        mark_job_failed(db, job_id=job_id, error="job.values 为空, 无字段可推", retry=False)
        return {"status": "failed", "error": "no values"}

    # 实时取 sku_master 以拿最新 out_sku_code / product_code / product_name
    # (enqueue 时的 metadata 可能已过期, 例如运营刚在吉客云补完外部码)
    sku_master_id = str(payload.get("sku_master_id") or "").strip()
    sku = db.get(models.SkuMaster, sku_master_id) if sku_master_id else None
    if sku is None:
        # 没拿到 sku, 用 enqueue 时的 metadata 兜底
        meta = job.metadata_json or {}
        out_sku_code = (meta.get("out_sku_code") or "").strip() if isinstance(meta.get("out_sku_code"), str) else ""
        product_code = (meta.get("product_code") or "").strip() if isinstance(meta.get("product_code"), str) else ""
        product_name = meta.get("product_name") or product_code
    else:
        out_sku_code = (getattr(sku, "out_sku_code", None) or "").strip()
        product_code = (getattr(sku, "product_code", None) or "").strip()
        product_name = getattr(sku, "product_name", None) or product_code

    # 攻击/并发保护: attempt + 锁状态
    job.attempt = int(job.attempt or 0) + 1
    job.last_attempt_at = _now_naive_utc()
    job.updated_at = _now_naive_utc()
    if job.status == "pending":
        job.status = "retrying"
    db.commit()

    try:
        client = build_default_client()
    except RuntimeError as exc:
        mark_job_failed(db, job_id=job_id, error=f"客户端初始化失败: {exc}", retry=False)
        return {"status": "failed", "error": str(exc)}

    # ---- 分流字段 ----
    flag_value = values.pop("flagData", None)
    other_values = {k: v for k, v in values.items() if v not in (None, "")}

    steps: List[Dict[str, Any]] = []

    # Step 1: 规格标记 → batchupdateflagbyskubarcode (条件: 有 flag 且 barcode)
    flag_biz = _build_flag_biz(barcode, flag_value)
    if flag_biz:
        steps.append({"step": "flag", **_call_one_step(
            client, api_method=API_BATCH_UPDATE_FLAG, biz=flag_biz, db=db)})

    # Step 2: 其他字段 → skuimportbatch (条件: 有非 flag 字段)
    if other_values:
        if not out_sku_code:
            # 缺 outSkuCode, 整个 step 跳过, 给清晰错误码引导运营补码
            steps.append({
                "step": "skuimport",
                "status": "needs_outsku_code",
                "error": "out_sku_code 为空, 请先在吉客云后台批量补外部编码 (吉客云那侧 sku 没补 outSkuCode 时本接口无法 update)",
                "api": API_SKU_IMPORT_BATCH,
            })
        elif not product_code:
            steps.append({
                "step": "skuimport",
                "status": "failed",
                "retry": False,
                "error": "product_code (goodsNo) 为空, 无法定位货品",
                "api": API_SKU_IMPORT_BATCH,
            })
        else:
            sk_biz = _build_skuimport_biz(
                out_sku_code=out_sku_code,
                goods_no=product_code,
                goods_name=product_name,
                sku_values=other_values,
            )
            steps.append({"step": "skuimport", **_call_one_step(
                client, api_method=API_SKU_IMPORT_BATCH, biz=sk_biz, db=db)})

    if not steps:
        mark_job_failed(db, job_id=job_id, error="无可推送字段 (flag 为空且 other 为空)", retry=False)
        return {"status": "failed", "error": "no pushable field"}

    # ---- 汇总 ----
    n_ok = sum(1 for s in steps if s.get("status") == "succeeded")
    n_skip_oc = sum(1 for s in steps if s.get("status") == "needs_outsku_code")
    n_fail = sum(1 for s in steps if s.get("status") == "failed")
    n_retry = sum(1 for s in steps if s.get("status") == "retry")
    total = len(steps)

    if n_retry:
        # 任一网络错: 整体 retrying (用最严的)
        first_retry = next(s for s in steps if s.get("status") == "retry")
        mark_job_failed(db, job_id=job_id,
                        error=f"NET retry: {first_retry.get('error')}", retry=True)
        return {"status": "retrying", "steps": steps, "summary": f"{n_ok}/{total} ok"}

    if n_fail:
        first_fail = next(s for s in steps if s.get("status") == "failed")
        mark_job_failed(db, job_id=job_id,
                        error=f"step({first_fail.get('step')}) FAIL: {first_fail.get('error')}",
                        retry=False)
        return {"status": "failed", "steps": steps, "summary": f"{n_ok}/{total} ok",
                "error": first_fail.get("error"),
                "biz_sub_code": first_fail.get("biz_sub_code")}

    if n_ok == total:
        mark_job_done(db, job_id=job_id, requested_by=requested_by)
        return {"status": "succeeded", "steps": steps, "summary": f"{n_ok}/{total} ok"}

    # 走到这: 没 fail / retry, 但有 needs_outsku_code (一定有 skip 且 ok+skip=total)
    if n_skip_oc and n_ok:
        # 部分成功 (flag 推了, skuimport 跳了): 算"半成功", 标 fail 但等运营补码
        mark_job_failed(
            db, job_id=job_id,
            error=f"PART OK: flag 推送成功, skuimport 跳过 (需补 outSkuCode)",
            retry=False,
        )
        return {"status": "needs_outsku_code", "steps": steps,
                "summary": f"{n_ok}/{total} ok, {n_skip_oc} 需补码"}
    # 只剩 needs_outsku_code 全部 skip
    mark_job_failed(
        db, job_id=job_id,
        error="needs_outsku_code: 请先在吉客云后台批量补 outSkuCode",
        retry=False,
    )
    return {"status": "needs_outsku_code", "steps": steps,
            "summary": f"0/{total} ok"}


def run_worker_once(
    db: Session,
    *,
    batch_size: int = 20,
    requested_by: Optional[str] = None,
) -> Dict[str, Any]:
    """手动批扫一次 — Phase B v1 的最小可用 worker.

    取最多 ``batch_size`` 条 status in (pending, retrying) + next_run_at <= now
    的 job, 串行调 push_one_job. 适合运营点按钮触发, 或外部 cron 通过
    POST /sku-master/erp-writeback/worker/run-once 调用.

    返回累计 succeeded / failed / retrying 计数以及每条 job 的简短结果,
    UI 直接展示给运营.

    注意:
    - 串行而非并行 — 避免短时间大量请求触发吉客云限流; batch_size 默认 20
      足以在 60s 内完成 (单条 push <2s + 网络抖动).
    - 真"自动调度"留给 Phase B v2 (systemd timer 调本接口即可).
    """
    bs = max(min(int(batch_size or 20), 200), 1)
    now = _now_naive_utc()
    rows = (
        db.query(models.IntegrationWritebackJob)
        .filter(
            models.IntegrationWritebackJob.source_system == SOURCE_SYSTEM,
            models.IntegrationWritebackJob.target_type == TARGET_TYPE,
            models.IntegrationWritebackJob.status.in_(("pending", "retrying")),
        )
        .order_by(
            models.IntegrationWritebackJob.next_run_at.asc().nulls_first(),
            models.IntegrationWritebackJob.created_at.asc(),
        )
        .limit(bs)
        .all()
    )

    job_ids = [str(r.id) for r in rows]
    results: List[Dict[str, Any]] = []
    counts: Dict[str, int] = {}

    for jid in job_ids:
        r = push_one_job(db, job_id=jid, requested_by=requested_by, force=False)
        st = str(r.get("status") or "unknown")
        counts[st] = counts.get(st, 0) + 1
        results.append(
            {
                "job_id": jid,
                "status": st,
                "biz_sub_code": r.get("biz_sub_code"),
                "error": r.get("error"),
            }
        )

    return {
        "scanned": len(job_ids),
        "batch_size": bs,
        "counts": counts,
        "results": results,
        "started_at": now.isoformat(),
        "finished_at": _now_naive_utc().isoformat(),
    }


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
    # 注意: push_one_job 已经把 attempt 自增了, 这里不再加
    job.last_attempt_at = _now_naive_utc()
    job.last_error = (error or "")[:4000]
    if retry and int(job.attempt or 0) < int(job.max_attempts or 5):
        job.status = "retrying"
    else:
        job.status = "failed"
    job.updated_at = _now_naive_utc()
    db.commit()
    return {"id": str(job.id), "status": job.status, "attempt": job.attempt}

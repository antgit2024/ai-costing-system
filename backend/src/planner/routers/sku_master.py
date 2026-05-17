from __future__ import annotations

import io
import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.orm import Session
import httpx

from ..dependencies import get_db_session
from .. import schemas
from ..schemas import PaginatedSkuMasterResponse, SkuMasterImportResponse, SkuMasterRead
from ..services import sku_master_service
from ..services import sku_master_image_storage
from ..services import erp_writeback_service
from ...config import settings
from .. import models

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/sku-master", tags=["SKU Master"])


@router.post("/import", response_model=SkuMasterImportResponse)
async def import_sku_master_xlsx(
    file: UploadFile = File(...),
    requested_by: str | None = Form(None),
    db: Session = Depends(get_db_session),
):
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Empty file")
    result = sku_master_service.import_erp_sku_master_xlsx(db, file_bytes=contents, requested_by=requested_by)
    return result


@router.get("", response_model=PaginatedSkuMasterResponse)
def list_sku_master(
    search: str | None = None,
    channel: str | None = None,
    match_status: str | None = None,
    target_kind: str | None = None,  # model|bundle|any
    bound_state: str | None = None,
    bound_model_id: str | None = None,
    bound_model_code: str | None = None,
    bound_version_id: str | None = None,
    bundle_bound_state: str | None = None,  # bound|unbound
    bundle_template_id: str | None = None,
    bundle_template_code: str | None = None,
    bundle_preset_selector: str | None = None,
    spec_mismatch: bool | None = None,
    data_quality_status: str | None = None,
    preparse_state: str | None = None,
    include_terms: str | None = None,
    exclude_terms: str | None = None,
    match_scope: str | None = None,
    shop_spec_code_kind: str | None = None,
    page: int = 1,
    page_size: int = 20,
    compute_total: bool = True,
    include_bindings: bool = True,
    include_parsed_fields: bool = True,
    include_shop_count: bool = False,
    db: Session = Depends(get_db_session),
):
    total, items = sku_master_service.list_sku_master(
        db,
        search=search,
        channel=channel,
        match_status=match_status,
        target_kind=target_kind,
        bound_state=bound_state,
        bound_model_id=bound_model_id,
        bound_model_code=bound_model_code,
        bound_version_id=bound_version_id,
        bundle_bound_state=bundle_bound_state,
        bundle_template_id=bundle_template_id,
        bundle_template_code=bundle_template_code,
        bundle_preset_selector=bundle_preset_selector,
        spec_mismatch=spec_mismatch,
        data_quality_status=data_quality_status,
        preparse_state=preparse_state,
        include_terms=include_terms,
        exclude_terms=exclude_terms,
        match_scope=match_scope,
        shop_spec_code_kind=shop_spec_code_kind,
        page=page,
        page_size=page_size,
        compute_total=compute_total,
        include_bindings=include_bindings,
        include_parsed_fields=include_parsed_fields,
        include_shop_count=include_shop_count,
    )
    return {"total": total, "page": page, "page_size": page_size, "items": items}


@router.get("/triple-tag-overview")
def triple_tag_overview(
    channel: str | None = None,
    db: Session = Depends(get_db_session),
):
    """三标签全局指标 — 商品档案顶部"指标条"用.

    系统标签 = 真源 (sys_bound 是 M4 反写的真正目标量)
    商家标签 = 输入材料 (干净/脏/空)
    ERP 标签 = 下游镜像 (反写完成度)
    见 services/sku_master_service.summarize_triple_tag_overview 详细注释.
    """
    return sku_master_service.summarize_triple_tag_overview(db, channel=channel)


@router.get("/shop-spec-code-summary")
def shop_spec_code_summary(
    channel: str | None = None,
    bound_state: str | None = None,
    db: Session = Depends(get_db_session),
):
    """Count of SKU master rows by shop_spec_code classification.

    Returns ``{"total": N, "structured": A, "platform": B, "malformed": C, "empty": D}``
    where ``structured`` rows are the only ones that can drive P0 anchor
    auto-binding. Used by the SKU master page strip to show coverage at a glance.
    """
    return sku_master_service.summarize_shop_spec_code(
        db, channel=channel, bound_state=bound_state
    )


@router.post("/{sku_master_id}/data-quality/recompute")
def recompute_data_quality(
    sku_master_id: str,
    payload: dict | None = None,
    db: Session = Depends(get_db_session),
):
    """重新评估单条 SKU 的"数据质量"标签（SPU 属性冲突）。

    供运营在 SKU 主档详情页"重新评估"按钮调用。会立刻刷新该 SKU 的
    ``metadata.data_quality_status`` 和 ``data_quality_evidence``。

    Body (optional): ``{"lookback_days": 90}``
    """
    from ..services import data_quality_service
    body = payload or {}
    lookback = body.get("lookback_days")
    try:
        lookback = int(lookback) if lookback is not None else 90
    except (TypeError, ValueError):
        lookback = 90
    evidence = data_quality_service.detect_for_one_sku(
        db,
        sku_master_id=str(sku_master_id),
        lookback_days=lookback,
        persist=True,
    )
    return {
        "sku_master_id": str(sku_master_id),
        "data_quality_status": "spu_attribute_conflict" if evidence else None,
        "data_quality_evidence": evidence,
    }


@router.post("/{sku_master_id}/suspect-misbind/resolve")
def resolve_suspect_misbind(
    sku_master_id: str,
    payload: dict | None = None,
    db: Session = Depends(get_db_session),
):
    """Operator marks "疑似绑错" as a false positive for this SKU.

    All shipment lines of this SKU stop showing the red "疑似绑错" tag /
    counting in 「只看疑似绑错」 until the binding changes again.

    Body (optional): ``{"requested_by": "...", "note": "..."}``
    """
    body = payload or {}
    return sku_master_service.resolve_suspect_misbind(
        db,
        sku_master_id=str(sku_master_id),
        requested_by=str(body.get("requested_by") or "").strip() or None,
        note=str(body.get("note") or "").strip() or None,
    )


@router.post("/{sku_master_id}/spec-mismatch/resolve")
def resolve_spec_mismatch(
    sku_master_id: str,
    payload: dict | None = None,
    db: Session = Depends(get_db_session),
):
    """Operator marks a previously flagged spec_mismatch as "ignored" because
    they have visually confirmed it's a false positive (字符顺序差异、颜色前缀差异 etc.).

    Sets ``metadata.spec_mismatch_resolved = True`` + audit fields. The next
    shipment ingest will:
      - keep the resolved flag if the new diff is still benign
      - auto-revoke it if a real ``dimension_mismatch`` shows up

    Body (optional): ``{"requested_by": "...", "note": "..."}``
    """
    body = payload or {}
    return sku_master_service.resolve_spec_mismatch(
        db,
        sku_master_id=str(sku_master_id),
        requested_by=str(body.get("requested_by") or "").strip() or None,
        note=str(body.get("note") or "").strip() or None,
    )


@router.get("/published-standard-models", response_model=schemas.PublishedStandardModelCandidateListResponse)
def list_published_standard_models(
    search: str | None = None,
    limit: int = 50,
    db: Session = Depends(get_db_session),
):
    items = sku_master_service.list_published_standard_model_candidates(db, search=search, limit=limit)
    return {"items": items}


@router.post("/bind-by-model", response_model=schemas.SkuMasterBindByModelResponse)
def bind_by_model(payload: schemas.SkuMasterBindByModelRequest, db: Session = Depends(get_db_session)):
    logger.info(
        "[bind-by-model] model_id=%s sku_count=%d allow_rebind=%s variant_code=%r",
        payload.model_id,
        len(payload.sku_master_ids or []),
        payload.allow_rebind,
        payload.variant_code,
    )
    try:
        return sku_master_service.bind_sku_master_by_model(
            db,
            model_id=payload.model_id,
            sku_master_ids=payload.sku_master_ids,
            requested_by=payload.requested_by,
            allow_rebind=payload.allow_rebind,
            variant_code=payload.variant_code,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/bind-by-model/preview", response_model=schemas.SkuMasterBindPreviewResponse)
def preview_bind_by_model(payload: schemas.SkuMasterBindByModelRequest, db: Session = Depends(get_db_session)):
    try:
        return sku_master_service.preview_bind_by_model(
            db,
            model_id=payload.model_id,
            sku_master_ids=payload.sku_master_ids,
            requested_by=payload.requested_by,
            allow_rebind=payload.allow_rebind,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/bind-by-model/preview/bulk", response_model=schemas.SkuMasterBindPreviewBulkResponse)
def preview_bind_by_model_bulk(payload: schemas.SkuMasterBindByModelBulkRequest, db: Session = Depends(get_db_session)):
    try:
        return sku_master_service.preview_bind_by_model_bulk(
            db,
            model_id=payload.model_id,
            requested_by=payload.requested_by,
            limit=payload.limit,
            bound_state=payload.bound_state,
            allow_rebind=payload.allow_rebind,
            search=payload.search,
            channel=payload.channel,
            match_status=payload.match_status,
            spec_mismatch=payload.spec_mismatch,
            preparse_state=payload.preparse_state,
            include_terms=payload.include_terms,
            exclude_terms=payload.exclude_terms,
            match_scope=payload.match_scope,
            bound_model_id=payload.bound_model_id,
            bound_model_code=payload.bound_model_code,
            bound_version_id=payload.bound_version_id,
            excluded_sku_master_ids=payload.excluded_sku_master_ids,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/bind-by-model/bulk", response_model=schemas.SkuMasterBindByModelBulkResponse)
def bind_by_model_bulk(payload: schemas.SkuMasterBindByModelBulkRequest, db: Session = Depends(get_db_session)):
    """
    Bind all unbound sku masters matched by current filters (server-side).
    This enables UI "implicit select all" across pages, with an exclusion list for unchecked rows.
    """
    try:
        return sku_master_service.bind_sku_master_by_model_bulk(
            db,
            model_id=payload.model_id,
            requested_by=payload.requested_by,
            limit=payload.limit,
            bound_state=payload.bound_state,
            allow_rebind=payload.allow_rebind,
            search=payload.search,
            channel=payload.channel,
            match_status=payload.match_status,
            spec_mismatch=payload.spec_mismatch,
            preparse_state=payload.preparse_state,
            include_terms=payload.include_terms,
            exclude_terms=payload.exclude_terms,
            match_scope=payload.match_scope,
            bound_model_id=payload.bound_model_id,
            bound_model_code=payload.bound_model_code,
            bound_version_id=payload.bound_version_id,
            excluded_sku_master_ids=payload.excluded_sku_master_ids,
            variant_code=payload.variant_code,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/update-field-bulk/preview", response_model=schemas.SkuMasterUpdateFieldBulkResponse)
def preview_update_field_bulk(
    payload: schemas.SkuMasterUpdateFieldBulkRequest,
    db: Session = Depends(get_db_session),
):
    """预演通用字段批量更新 — dry_run=true, 不写库, 仅返回影响行数 / 错误.

    用于商品档案"批改前看影响多少条"的预览面板.
    """
    try:
        return sku_master_service.update_sku_master_field_bulk(
            db,
            field_name=payload.field_name,
            new_value=payload.new_value,
            mode=payload.mode,
            requested_by=payload.requested_by,
            dry_run=True,
            sku_master_ids=list(payload.sku_master_ids or []),
            limit=payload.limit,
            search=payload.search,
            channel=payload.channel,
            match_status=payload.match_status,
            spec_mismatch=payload.spec_mismatch,
            preparse_state=payload.preparse_state,
            include_terms=payload.include_terms,
            exclude_terms=payload.exclude_terms,
            match_scope=payload.match_scope,
            bound_state=payload.bound_state,
            bound_model_id=payload.bound_model_id,
            bound_model_code=payload.bound_model_code,
            bound_version_id=payload.bound_version_id,
            bundle_bound_state=payload.bundle_bound_state,
            bundle_template_id=payload.bundle_template_id,
            bundle_preset_selector=payload.bundle_preset_selector,
            excluded_sku_master_ids=list(payload.excluded_sku_master_ids or []),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/update-field-bulk", response_model=schemas.SkuMasterUpdateFieldBulkResponse)
def update_field_bulk(
    payload: schemas.SkuMasterUpdateFieldBulkRequest,
    db: Session = Depends(get_db_session),
):
    """通用字段批量更新 — 商品档案 / 商品关联 共用入口.

    安全策略: 服务端 _UPDATE_BULK_ALLOWED_FIELDS 白名单, 仅允许业务字段
    (production_process / metadata.erp.sku_flag). 严禁碰 binding 字段.

    两种调用方式:
    1. 单条/精确多选: 传 sku_master_ids, 忽略筛选
    2. 跨页隐式全选: 不传 sku_master_ids, 用 search/channel/... 筛选 + limit 分批
       前端"一键跑完"按 200/批循环调用直到 has_more=false
    """
    try:
        return sku_master_service.update_sku_master_field_bulk(
            db,
            field_name=payload.field_name,
            new_value=payload.new_value,
            mode=payload.mode,
            requested_by=payload.requested_by,
            dry_run=bool(payload.dry_run),
            sku_master_ids=list(payload.sku_master_ids or []),
            limit=payload.limit,
            search=payload.search,
            channel=payload.channel,
            match_status=payload.match_status,
            spec_mismatch=payload.spec_mismatch,
            preparse_state=payload.preparse_state,
            include_terms=payload.include_terms,
            exclude_terms=payload.exclude_terms,
            match_scope=payload.match_scope,
            bound_state=payload.bound_state,
            bound_model_id=payload.bound_model_id,
            bound_model_code=payload.bound_model_code,
            bound_version_id=payload.bound_version_id,
            bundle_bound_state=payload.bundle_bound_state,
            bundle_template_id=payload.bundle_template_id,
            bundle_preset_selector=payload.bundle_preset_selector,
            excluded_sku_master_ids=list(payload.excluded_sku_master_ids or []),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/edit-form", response_model=schemas.SkuMasterEditFormResponse)
def edit_form(
    payload: schemas.SkuMasterEditFormRequest,
    db: Session = Depends(get_db_session),
):
    """抽屉「字段编辑」统一表单 — 单条 SKU 4 字段一次保存 + 自动重识别.

    见 ``sku_master_service.edit_sku_form`` 的 docstring. 配套前端
    ProductInfoDetailDrawer.tsx 的「字段编辑」卡片.
    """
    try:
        return sku_master_service.edit_sku_form(
            db,
            sku_master_id=payload.sku_master_id,
            requested_by=payload.requested_by,
            update_fields=list(payload.update_fields or []),
            production_process=payload.production_process,
            sku_flag=payload.sku_flag,
            shop_spec_code=payload.shop_spec_code,
            spec_text=payload.spec_text,
            trigger_rebind=payload.trigger_rebind,
            dry_run=payload.dry_run,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# -----------------------------------------------------------------------------
# M6 ERP 反写: Excel 模板 (方案 B) + 队列 (方案 A) + 反写历史
# 见 services/erp_writeback_service.py
# -----------------------------------------------------------------------------


@router.post("/erp-writeback/export-excel")
def erp_writeback_export_excel(
    payload: schemas.ErpWritebackExcelRequest,
    db: Session = Depends(get_db_session),
):
    """按 sku_master_ids 生成吉客云「批量修改货品」兼容 xlsx, 二进制下载.

    业务流程: 运营选好行 → 点「下载反写 Excel」 → 在吉客云后台导入即可.
    """
    if not payload.sku_master_ids:
        raise HTTPException(status_code=400, detail="sku_master_ids 不能为空")
    try:
        xlsx_bytes, summary = erp_writeback_service.build_writeback_excel(
            db,
            sku_master_ids=list(payload.sku_master_ids),
            fields=list(payload.fields) if payload.fields else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    filename = summary.get("filename") or "jackyun_writeback.xlsx"
    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        # 把汇总信息也带回去, 让前端能 toast「已生成 N 行」
        "X-Writeback-Total-Rows": str(summary.get("total_rows", 0)),
        "X-Writeback-Fields": ",".join(summary.get("fields", [])),
        "X-Writeback-Skipped": str(summary.get("skipped_missing_barcode", 0)),
    }
    return StreamingResponse(
        io.BytesIO(xlsx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )


@router.post("/erp-writeback/enqueue", response_model=schemas.ErpWritebackEnqueueResponse)
def erp_writeback_enqueue(
    payload: schemas.ErpWritebackEnqueueRequest,
    db: Session = Depends(get_db_session),
):
    """把反写意图入队 ``integration_writeback_jobs``.

    Worker 由后续模块实现; 当前 enqueue 后 job 留在 ``pending``.
    用于建立反写历史 + 未来 API 直推.
    """
    if not payload.sku_master_ids:
        raise HTTPException(status_code=400, detail="sku_master_ids 不能为空")
    try:
        return erp_writeback_service.enqueue_writeback_jobs(
            db,
            sku_master_ids=list(payload.sku_master_ids),
            fields=list(payload.fields) if payload.fields else None,
            requested_by=payload.requested_by,
            dry_run=bool(payload.dry_run),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get(
    "/{sku_id}/erp-writeback/history",
    response_model=schemas.ErpWritebackHistoryResponse,
)
def erp_writeback_history(
    sku_id: str,
    limit: int = 50,
    db: Session = Depends(get_db_session),
):
    """单条 SKU 的反写历史 (供抽屉「反写历史」Tab)."""
    items = erp_writeback_service.list_jobs_for_sku(
        db,
        sku_master_id=sku_id,
        limit=limit,
    )
    return schemas.ErpWritebackHistoryResponse(sku_master_id=sku_id, items=items)


@router.get(
    "/erp-writeback/jobs",
    response_model=schemas.ErpWritebackJobsListResponse,
)
def erp_writeback_jobs_list(
    status: Optional[str] = None,
    search: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
    db: Session = Depends(get_db_session),
):
    """全局反写队列 (供「反写队列」抽屉/页面).

    - status: pending / retrying / succeeded / failed / superseded (多个用 "," 分隔)
    - search: 模糊匹配 erp_sku_barcode / product_code / product_name / out_sku_code
    """
    data = erp_writeback_service.list_writeback_jobs(
        db,
        status=status,
        search=search,
        page=page,
        page_size=page_size,
    )
    return data


@router.post("/erp-writeback/jobs/{job_id}/push")
def erp_writeback_push_one(
    job_id: str,
    force: bool = False,
    requested_by: Optional[str] = None,
    db: Session = Depends(get_db_session),
):
    """同步推送单条 job 到吉客云 (供「立刻推送」按钮 + 后续 worker 复用).

    - 返回 push_one_job 的真实结果, 包含 status / error / biz_sub_code / biz
    - force=True 时允许推 succeeded / failed / superseded 状态的 job (运营手动重试)
    """
    result = erp_writeback_service.push_one_job(
        db,
        job_id=job_id,
        requested_by=requested_by,
        force=force,
    )
    return result


@router.post("/bind-by-bundle", response_model=schemas.SkuMasterBindByBundleTemplateResponse)
def bind_by_bundle(payload: schemas.SkuMasterBindByBundleTemplateRequest, db: Session = Depends(get_db_session)):
    try:
        return sku_master_service.bind_sku_master_by_bundle_template(
            db,
            template_id=payload.template_id,
            preset_selector=payload.preset_selector,
            sku_master_ids=payload.sku_master_ids,
            requested_by=payload.requested_by,
            allow_rebind=payload.allow_rebind,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/bind-by-bundle/preview", response_model=schemas.SkuMasterBindPreviewResponse)
def preview_bind_by_bundle(payload: schemas.SkuMasterBindByBundleTemplateRequest, db: Session = Depends(get_db_session)):
    try:
        return sku_master_service.preview_bind_by_bundle_template(
            db,
            template_id=payload.template_id,
            preset_selector=payload.preset_selector,
            sku_master_ids=payload.sku_master_ids,
            requested_by=payload.requested_by,
            allow_rebind=payload.allow_rebind,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/bind-by-bundle/preview/bulk", response_model=schemas.SkuMasterBindPreviewBulkResponse)
def preview_bind_by_bundle_bulk(payload: schemas.SkuMasterBindByBundleTemplateBulkRequest, db: Session = Depends(get_db_session)):
    try:
        return sku_master_service.preview_bind_by_bundle_template_bulk(
            db,
            template_id=payload.template_id,
            preset_selector=payload.preset_selector,
            requested_by=payload.requested_by,
            limit=payload.limit,
            bound_state=payload.bound_state,
            allow_rebind=payload.allow_rebind,
            search=payload.search,
            channel=payload.channel,
            match_status=payload.match_status,
            spec_mismatch=payload.spec_mismatch,
            preparse_state=payload.preparse_state,
            include_terms=payload.include_terms,
            exclude_terms=payload.exclude_terms,
            match_scope=payload.match_scope,
            bound_model_id=payload.bound_model_id,
            bound_model_code=payload.bound_model_code,
            bound_version_id=payload.bound_version_id,
            excluded_sku_master_ids=payload.excluded_sku_master_ids,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/bind-by-bundle/bulk", response_model=schemas.SkuMasterBindByBundleTemplateBulkResponse)
def bind_by_bundle_bulk(payload: schemas.SkuMasterBindByBundleTemplateBulkRequest, db: Session = Depends(get_db_session)):
    try:
        return sku_master_service.bind_sku_master_by_bundle_template_bulk(
            db,
            template_id=payload.template_id,
            preset_selector=payload.preset_selector,
            requested_by=payload.requested_by,
            limit=payload.limit,
            bound_state=payload.bound_state,
            allow_rebind=payload.allow_rebind,
            search=payload.search,
            channel=payload.channel,
            match_status=payload.match_status,
            spec_mismatch=payload.spec_mismatch,
            preparse_state=payload.preparse_state,
            include_terms=payload.include_terms,
            exclude_terms=payload.exclude_terms,
            match_scope=payload.match_scope,
            bound_model_id=payload.bound_model_id,
            bound_model_code=payload.bound_model_code,
            bound_version_id=payload.bound_version_id,
            excluded_sku_master_ids=payload.excluded_sku_master_ids,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/unbind", response_model=schemas.SkuMasterUnbindResponse)
def unbind_sku_masters(payload: schemas.SkuMasterUnbindRequest, db: Session = Depends(get_db_session)):
    try:
        return sku_master_service.unbind_sku_masters(
            db,
            sku_master_ids=payload.sku_master_ids,
            requested_by=payload.requested_by,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/generate-preparse-and-snapshots", response_model=schemas.SkuMasterGeneratePreparseAndSnapshotsResponse)
def generate_preparse_and_snapshots(
    payload: schemas.SkuMasterGeneratePreparseAndSnapshotsRequest,
    db: Session = Depends(get_db_session),
):
    try:
        return sku_master_service.generate_preparse_and_snapshots(
            db,
            sku_master_ids=payload.sku_master_ids,
            operator_id=payload.operator_id,
            limit_per_sku=payload.limit_per_sku,
            overwrite=bool(payload.overwrite),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/auto-bind/preview", response_model=schemas.SkuMasterAutoBindPreviewResponse)
def auto_bind_preview(payload: schemas.SkuMasterAutoBindPreviewRequest, db: Session = Depends(get_db_session)):
    return sku_master_service.auto_bind_preview(db, limit=payload.limit, scan_limit=payload.scan_limit)


@router.post("/auto-bind/execute", response_model=schemas.SkuMasterAutoBindExecuteResponse)
def auto_bind_execute(payload: schemas.SkuMasterAutoBindExecuteRequest, db: Session = Depends(get_db_session)):
    return sku_master_service.auto_bind_execute(
        db,
        limit=payload.limit,
        requested_by=payload.requested_by,
        sku_master_ids=payload.sku_master_ids,
        scan_limit=50000,
    )


# ----------------------------------------------------------------------------
# SKU Governance (Sprint 2-3 of "SKU 治理与按需建模")
#
# IMPORTANT: these endpoints MUST be registered BEFORE the catch-all
# ``GET /{sku_id}`` route below, otherwise FastAPI will treat
# "governance" as a path parameter and return 404 ("SKU master not
# found") for legitimate governance traffic. The lesson cost us one
# debugging round, hence this comment block.
# ----------------------------------------------------------------------------


@router.post(
    "/governance",
    response_model=schemas.SkuGovernanceSetResponse,
    summary="批量设置 SKU 治理状态(unmanaged/auto_bound/pending_model/do_not_model)",
)
def set_sku_governance(
    payload: schemas.SkuGovernanceSetRequest,
    db: Session = Depends(get_db_session),
):
    """Bulk-update governance_status for the given barcodes.

    UI usage:
      - BatchWorkbench exception queue: 4 action buttons each call this
        with a single (or selected-batch) sku_codes + the right status.
      - "长尾 SKU" tab revert: status=unmanaged.

    Side-effects: writes governance_status / decided_at / decided_by /
    note + appends to governance_history (audit trail) on each row's
    metadata_json.
    """
    try:
        counters = sku_master_service.set_sku_governance(
            db,
            sku_codes=payload.sku_codes,
            status=payload.status,
            decided_by=payload.decided_by,
            note=payload.note,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    db.commit()
    return counters


@router.get(
    "/governance",
    response_model=schemas.SkuGovernanceListResponse,
    summary="按治理状态分页列出 SKU(带最近 N 天发货统计供运营排序)",
)
def list_sku_governance(
    status: str,
    page: int = 1,
    page_size: int = 50,
    order_by: str = "shipment_score",
    sales_window_days: int = 30,
    db: Session = Depends(get_db_session),
):
    """Backlog list — used by the new "建模 Backlog" / "长尾 SKU" tabs.

    Each item carries ``revenue_window`` so the UI can sort by sales
    potential and surface high-impact SKUs first.
    """
    try:
        return sku_master_service.list_governance_backlog(
            db,
            status=status,
            page=page,
            page_size=page_size,
            order_by=order_by,
            sales_window_days=sales_window_days,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post(
    "/governance/promote-from-model",
    response_model=schemas.SkuGovernancePromoteResponse,
    summary="模型发布完成后,将相关 SKU 从 pending_model 提升至 auto_bound",
)
def promote_governance_from_model(
    payload: schemas.SkuGovernancePromoteRequest,
    db: Session = Depends(get_db_session),
):
    """Called by the model-publish flow (or manually from ops UI) to
    take SKUs that were sitting in the modeling backlog and mark them
    as bound. Idempotent.
    """
    counters = sku_master_service.auto_promote_pending_model(
        db,
        sku_codes=payload.sku_codes,
        decided_by=payload.decided_by,
    )
    db.commit()
    return counters


@router.post(
    "/long-tail-category",
    response_model=schemas.SkuLongTailCategorySetResponse,
    summary="批量给 SKU 标 long_tail_category(对应长尾策略表的某条品类; 留空清除)",
)
def set_sku_long_tail_category(
    payload: schemas.SkuLongTailCategorySetRequest,
    db: Session = Depends(get_db_session),
):
    """Issue 28 follow-up: write SkuMaster.metadata_json.long_tail_category
    so the long-tail snapshot picks the matching strategy regardless of
    keywords. Pass ``category=""`` (or null) to clear the override.
    """
    try:
        counters = sku_master_service.set_sku_long_tail_category(
            db,
            sku_codes=payload.sku_codes,
            category=payload.category,
            actor=payload.actor,
            note=payload.note,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    db.commit()
    return counters


@router.post(
    "/long-tail-category/auto-suggest/preview",
    response_model=schemas.SkuLongTailCategoryAutoSuggestPreviewResponse,
    summary="按策略关键字扫描长尾池, 返回建议的品类候选(不写入)",
)
def auto_suggest_long_tail_category_preview(
    payload: schemas.SkuLongTailCategoryAutoSuggestRequest,
    db: Session = Depends(get_db_session),
):
    """Issue 28 follow-up: scan long-tail SKUs and produce keyword-based
    ``long_tail_category`` suggestions without writing.

    Use this to preview "if I clicked auto-apply, which SKUs would get
    which category?" — the response is what the UI lists in the candidate
    drawer; the user picks "全部采纳" (calls /execute) or selects a
    subset (calls /set with sku_codes + chosen category).
    """
    return sku_master_service.auto_suggest_long_tail_category(
        db,
        sku_codes=payload.sku_codes,
        include_already_labeled=payload.include_already_labeled,
        limit=payload.limit,
    )


@router.post(
    "/long-tail-category/auto-suggest/execute",
    response_model=schemas.SkuLongTailCategoryAutoSuggestExecuteResponse,
    summary="一键自动标长尾品类(扫描 + 按策略关键字写入 metadata.long_tail_category)",
)
def auto_suggest_long_tail_category_execute(
    payload: schemas.SkuLongTailCategoryAutoSuggestRequest,
    db: Session = Depends(get_db_session),
):
    """One-shot apply of the preview above. Each candidate gets
    ``set_sku_long_tail_category(category=suggested)`` with
    ``actor=payload.actor`` (defaults to 'auto-suggest') and
    ``note='auto-applied via keyword match'`` so audit history records
    that this label came from the auto-suggester (not a human).
    """
    result = sku_master_service.auto_apply_long_tail_category(
        db,
        sku_codes=payload.sku_codes,
        include_already_labeled=payload.include_already_labeled,
        limit=payload.limit,
        actor=payload.actor,
    )
    db.commit()
    return result


@router.get("/{sku_id}", response_model=SkuMasterRead)
def get_sku_master(sku_id: str, db: Session = Depends(get_db_session)):
    row = sku_master_service.get_sku_master(db, sku_id)
    if not row:
        raise HTTPException(status_code=404, detail="SKU master not found")
    return row


def _download_image(url: str) -> tuple[bytes, str | None]:
    """
    Isolated for tests (can be monkeypatched).
    """
    with httpx.Client(timeout=20.0, follow_redirects=True) as client:
        resp = client.get(url)
    resp.raise_for_status()
    return resp.content, resp.headers.get("content-type")


@router.get("/{sku_id}/images/{kind}")
def get_sku_master_image(
    sku_id: str,
    kind: str,
    force_refresh: int | None = None,
    db: Session = Depends(get_db_session),
):
    """
    Proxy + on-demand local caching for SKU master images (spec/product).
    Use this instead of directly loading 3rd-party (e.g. alicdn) URLs on factory scan pages.
    """
    kind2 = (kind or "").strip().lower()
    if kind2 not in ("spec", "product"):
        raise HTTPException(status_code=400, detail="kind must be spec|product")

    row = db.get(models.SkuMaster, sku_id)
    if not row or getattr(row, "is_archived", False):
        raise HTTPException(status_code=404, detail="SKU master not found")

    images = getattr(row, "images_json", {}) or {}
    if not isinstance(images, dict):
        images = {}
    key = "spec_image" if kind2 == "spec" else "product_image"
    source_url = (images.get(key) or "").strip()
    if not source_url:
        raise HTTPException(status_code=404, detail="Image not found")

    meta = getattr(row, "metadata_json", {}) or {}
    if not isinstance(meta, dict):
        meta = {}

    if settings.planner_persist_sku_images and not force_refresh:
        ref = sku_master_image_storage.get_local_image_ref(meta, kind2)
        if ref and ref.path:
            try:
                data = sku_master_image_storage.read_local_bytes(ref)
                return Response(content=data, media_type=ref.content_type or "application/octet-stream")
            except Exception:
                # fall back to remote fetch
                pass

    # Remote fetch (and optionally persist)
    try:
        data, ct = _download_image(source_url)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Failed to fetch image: {exc}") from exc

    if settings.planner_persist_sku_images:
        ref2 = sku_master_image_storage.persist_bytes(
            sku_master_id=row.id,
            kind=kind2,
            source_url=source_url,
            content=data,
            content_type=ct,
        )
        sku_master_image_storage.set_local_image_ref(meta, kind2, ref2)
        row.metadata_json = meta
        db.add(row)
        db.commit()
        # best-effort cleanup
        sku_master_image_storage.maybe_cleanup()

    return Response(content=data, media_type=ct or "application/octet-stream")

@router.get("/by-barcode/{barcode}", response_model=schemas.SkuMasterScanResponse)
def get_sku_master_by_barcode(
    barcode: str,
    channel: str | None = None,
    limit: int = 20,
    db: Session = Depends(get_db_session),
):
    """
    Scan/production use case: query sku master by ERP barcode (SSOT).
    Also returns shop-level SKUs (platform_sku_id dimension) when table/migration exists.
    """
    row = sku_master_service.get_by_barcode(db, barcode)
    if not row:
        raise HTTPException(status_code=404, detail="SKU master not found")
    shop_skus = []
    try:
        shop_skus = sku_master_service.list_shop_skus_by_barcode(
            db, erp_sku_barcode=barcode, channel=channel, limit=limit
        )
    except Exception:
        shop_skus = []
    return {"sku_master": row, "shop_skus": shop_skus}


@router.post("/{sku_id}/spec-preparse", response_model=schemas.SkuMasterSpecPreparseSaveResponse)
def save_spec_preparse(
    sku_id: str,
    payload: schemas.SkuMasterSpecPreparseSaveRequest,
    db: Session = Depends(get_db_session),
):
    try:
        return sku_master_service.save_spec_preparse(
            db,
            sku_id=sku_id,
            spec_text=payload.spec_text,
            width_cm=payload.width_cm,
            height_cm=payload.height_cm,
            diameter_cm=payload.diameter_cm,
            requested_by=payload.requested_by,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/spec-preparse/bulk", response_model=schemas.SkuMasterSpecPreparseBulkResponse)
def bulk_save_spec_preparse(
    payload: schemas.SkuMasterSpecPreparseBulkRequest,
    db: Session = Depends(get_db_session),
):
    try:
        return sku_master_service.bulk_save_spec_preparse(
            db,
            limit=payload.limit,
            search=payload.search,
            channel=payload.channel,
            match_status=payload.match_status,
            target_kind=payload.target_kind,
            bundle_bound_state=payload.bundle_bound_state,
            bundle_template_id=payload.bundle_template_id,
            bundle_template_code=payload.bundle_template_code,
            bundle_preset_selector=payload.bundle_preset_selector,
            include_terms=payload.include_terms,
            exclude_terms=payload.exclude_terms,
            match_scope=payload.match_scope,
            bound_model_id=payload.bound_model_id,
            bound_model_code=payload.bound_model_code,
            bound_version_id=payload.bound_version_id,
            preparse_state=payload.preparse_state,
            cursor_id=payload.cursor_id,
            excluded_sku_ids=payload.excluded_sku_ids,
            skip_if_same_hash=payload.skip_if_same_hash,
            requested_by=payload.requested_by,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/spec-preparse/preview", response_model=schemas.SkuMasterSpecPreparsePreviewResponse)
def preview_spec_preparse(
    payload: schemas.SkuMasterSpecPreparsePreviewRequest,
    db: Session = Depends(get_db_session),
):
    return sku_master_service.preview_spec_preparse(
        db,
        limit=payload.limit,
        search=payload.search,
        channel=payload.channel,
        match_status=payload.match_status,
        target_kind=payload.target_kind,
        bundle_bound_state=payload.bundle_bound_state,
        bundle_template_id=payload.bundle_template_id,
        bundle_template_code=payload.bundle_template_code,
        bundle_preset_selector=payload.bundle_preset_selector,
        include_terms=payload.include_terms,
        exclude_terms=payload.exclude_terms,
        match_scope=payload.match_scope,
        bound_model_id=payload.bound_model_id,
        bound_model_code=payload.bound_model_code,
        bound_version_id=payload.bound_version_id,
        preparse_state=payload.preparse_state,
    )


@router.post("/spec-preparse/execute", response_model=schemas.SkuMasterSpecPreparseExecuteResponse)
def execute_spec_preparse(
    payload: schemas.SkuMasterSpecPreparseExecuteRequest,
    db: Session = Depends(get_db_session),
):
    return sku_master_service.execute_spec_preparse(
        db,
        sku_ids=payload.sku_ids,
        skip_if_same_hash=payload.skip_if_same_hash,
        requested_by=payload.requested_by,
    )



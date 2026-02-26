from __future__ import annotations

import os
import time
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .database import get_db
from .planner import models, schemas
from .planner.services import material_service
from .planner.services import product_model_service
from .planner.services import process_module_service


def now_ms() -> int:
    return int(time.time() * 1000)


class ActionIn(BaseModel):
    schema_version: str = "1.0"
    action_id: str
    idempotency_key: str
    trace_id: str
    type: str = "project_call"
    target: str
    name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)
    timeout_ms: int = 30_000
    actor: Optional[Dict[str, Any]] = None
    source: Optional[Dict[str, Any]] = None


router = APIRouter(prefix="/v1/projects/ai-costing-system", tags=["upstream-actions"])


def _allowed_mm_channel_ids() -> set[str]:
    raw = (os.getenv("AI_COSTING_SYSTEM_ALLOWED_MM_CHANNEL_IDS", "") or "").strip()
    if not raw:
        return set()
    return {x.strip() for x in raw.split(",") if x.strip()}


def _require_mattermost_channel_gate(action: ActionIn) -> None:
    """
    门禁（可选开启）：
      - 配置 AI_COSTING_SYSTEM_ALLOWED_MM_CHANNEL_IDS 后：
        - 允许：source.channel_type == "D"（私聊 DM）
        - 允许：source.channel_id 在 allowlist 中（指定频道）
        - 其他：403
    """
    allow = _allowed_mm_channel_ids()
    if not allow:
        return
    src = action.source or {}
    if (src.get("system") or "mattermost") != "mattermost":
        return
    ctype = (src.get("channel_type") or "").strip().upper()
    if ctype == "D":
        return
    cid = (src.get("channel_id") or "").strip()
    if cid and cid in allow:
        return
    raise HTTPException(status_code=403, detail="forbidden: channel is not allowed for ai-costing-system")


def _require_headers_match(action: ActionIn, *, x_trace_id: str, x_idempotency_key: str) -> None:
    if x_trace_id != action.trace_id:
        raise HTTPException(status_code=400, detail="trace_id mismatch between header and body")
    if x_idempotency_key != action.idempotency_key:
        raise HTTPException(status_code=400, detail="idempotency_key mismatch between header and body")


@router.post("/actions")
def run_project_action(
    action: ActionIn,
    x_trace_id: str = Header(alias="X-Trace-Id"),
    x_idempotency_key: str = Header(alias="X-Idempotency-Key"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    _require_headers_match(action, x_trace_id=x_trace_id, x_idempotency_key=x_idempotency_key)
    if action.target != "ai-costing-system":
        raise HTTPException(status_code=400, detail="target mismatch")
    _require_mattermost_channel_gate(action)

    started = now_ms()
    status = "succeeded"
    result_text = ""
    result_json: Dict[str, Any] = {}
    error: Optional[Dict[str, Any]] = None

    try:
        name = (action.name or "").strip()
        args = action.arguments or {}

        if name == "ping":
            result_text = "pong"
            result_json = {"ok": True}

        elif name in ("material.search", "materials.search", "material.list", "materials.list"):
            q = (args.get("q") or args.get("search") or "").strip() or None
            page = int(args.get("page") or 1)
            page_size = int(args.get("page_size") or 20)
            page = max(1, page)
            page_size = max(1, min(200, page_size))
            # 默认只查启用的物料
            is_active = args.get("is_active")
            if is_active is None:
                is_active = True
            elif isinstance(is_active, str):
                is_active = is_active.lower() in ("true", "1", "yes")

            filters = material_service.MaterialFilters(search=q, is_active=is_active)
            total, items = material_service.list_materials(db, filters=filters, page=page, page_size=page_size)
            reads = [schemas.MaterialRead.from_orm(m) for m in items]
            top = reads[: min(len(reads), 5)]

            lines = [f"materials.search q={q or ''} total={total} page={page} page_size={page_size}"]
            for m in top:
                img = (m.images or [None])[0]
                lines.append(f"- {m.material_code} {m.material_name} ({m.material_type}) img={img or ''}")
            result_text = "\n".join(lines)
            result_json = {
                "q": q,
                "total": total,
                "page": page,
                "page_size": page_size,
                "items": [m.dict(by_alias=True) for m in reads],
            }

        elif name in ("material.get", "materials.get", "material.by_code"):
            material_id = (args.get("material_id") or "").strip()
            material_code = (args.get("material_code") or args.get("code") or "").strip()
            if not material_id and not material_code:
                raise HTTPException(status_code=400, detail="material_id or material_code is required")

            material = None
            if material_id:
                material = db.get(models.Material, material_id)
            if material is None and material_code:
                material = (
                    db.query(models.Material)
                    .filter(
                        models.Material.is_archived.is_(False),
                        models.Material.material_code == material_code,
                    )
                    .first()
                )
            if material is None or getattr(material, "is_archived", False):
                raise HTTPException(status_code=404, detail="Material not found")

            m = schemas.MaterialRead.from_orm(material)
            img = (m.images or [None])[0]
            result_text = f"{m.material_code} {m.material_name} ({m.material_type}) img={img or ''}"
            result_json = {"material": m.dict(by_alias=True)}

        elif name in ("product.search", "products.search", "product.list", "products.list"):
            q = (args.get("q") or args.get("search") or "").strip() or None
            page = int(args.get("page") or 1)
            page_size = int(args.get("page_size") or 20)
            page = max(1, page)
            page_size = max(1, min(200, page_size))

            filters = product_model_service.ProductModelFilters(search=q)
            total, items = product_model_service.list_models(db, filters=filters, page=page, page_size=page_size)
            reads = [schemas.ProductModelRead.from_orm(m) for m in items]

            lines = [f"products.search q={q or ''} total={total} page={page} page_size={page_size}"]
            for m in reads[:5]:
                lines.append(f"- {m.model_code} {m.model_name} ({m.category or ''})")
            result_text = "\n".join(lines)
            result_json = {
                "q": q,
                "total": total,
                "page": page,
                "page_size": page_size,
                "items": [m.dict(by_alias=True) for m in reads],
            }

        elif name in ("product.get", "products.get", "product.by_code"):
            model_id = (args.get("model_id") or "").strip()
            model_code = (args.get("model_code") or args.get("code") or "").strip()
            if not model_id and not model_code:
                raise HTTPException(status_code=400, detail="model_id or model_code is required")

            product = None
            if model_id:
                product = product_model_service.get_model(db, model_id)
            if product is None and model_code:
                product = (
                    db.query(models.ProductModel)
                    .filter(
                        models.ProductModel.is_archived.is_(False),
                        models.ProductModel.model_code == model_code,
                    )
                    .first()
                )
            if product is None:
                raise HTTPException(status_code=404, detail="Product model not found")

            m = schemas.ProductModelRead.from_orm(product)
            result_text = f"{m.model_code} {m.model_name} ({m.category or ''})"
            result_json = {"product": m.dict(by_alias=True)}

        elif name in ("process_module.search", "process_modules.search", "process_module.list"):
            q = (args.get("q") or args.get("search") or "").strip() or None
            page = int(args.get("page") or 1)
            page_size = int(args.get("page_size") or 20)
            page = max(1, page)
            page_size = max(1, min(200, page_size))
            category = (args.get("category") or "").strip() or None

            filters = process_module_service.ProcessModuleFilters(search=q, category=category)
            total, items = process_module_service.list_modules(db, filters=filters, page=page, page_size=page_size)

            lines = [f"process_modules.search q={q or ''} total={total} page={page}"]
            items_out = []
            for m in items:
                mat_count = len(m.materials) if m.materials else 0
                step_count = len(m.steps) if m.steps else 0
                lines.append(f"- {m.module_code} {m.module_name} ({m.category or ''})")
                d = schemas.ProcessModuleSummaryRead.from_orm(m).dict(by_alias=True)
                d["material_count"] = mat_count
                d["step_count"] = step_count
                items_out.append(d)

            result_json = {
                "q": q,
                "total": total,
                "page": page,
                "page_size": page_size,
                "items": items_out,
            }

        elif name in ("process_module.get", "process_modules.get", "process_module.by_code"):
            module_id = (args.get("module_id") or args.get("id") or "").strip()
            module_code = (args.get("module_code") or args.get("code") or "").strip()
            if not module_id and not module_code:
                raise HTTPException(status_code=400, detail="module_id or module_code is required")

            module = None
            if module_id:
                module = db.get(models.ProcessModule, module_id)
            if module is None and module_code:
                module = (
                    db.query(models.ProcessModule)
                    .filter(
                        models.ProcessModule.is_archived.is_(False),
                        models.ProcessModule.module_code == module_code,
                    )
                    .first()
                )
            if module is None or getattr(module, "is_archived", False):
                raise HTTPException(status_code=404, detail="Process module not found")

            m = schemas.ProcessModuleDetailRead.from_orm(module)
            materials_summary = ", ".join([f"{mat.material_name or mat.material_code}" for mat in m.materials[:5]])
            if len(m.materials) > 5:
                materials_summary += f" +{len(m.materials)-5}..."
            steps_summary = ", ".join([f"{s.team_name or s.description or '工序'}" for s in m.steps[:5]])
            if len(m.steps) > 5:
                steps_summary += f" +{len(m.steps)-5}..."
            total_minutes = sum(float(s.work_minutes or 0) for s in m.steps)

            result_text = f"{m.module_code} {m.module_name} 物料={len(m.materials)} 工序={len(m.steps)} 总工时={total_minutes:.1f}分"
            d = m.dict(by_alias=True)
            d["material_count"] = len(m.materials)
            d["step_count"] = len(m.steps)
            d["materials_summary"] = materials_summary
            d["steps_summary"] = steps_summary
            d["total_work_minutes"] = total_minutes
            result_json = {"process_module": d}

        else:
            raise HTTPException(status_code=404, detail=f"unknown action name: {name}")

    except HTTPException as e:
        status = "failed"
        error = {"type": "HTTPException", "status_code": e.status_code, "detail": e.detail}
        result_text = f"error: {e.detail}"
    except Exception as e:  # noqa: BLE001
        status = "failed"
        error = {"type": type(e).__name__, "message": str(e)}
        result_text = "error"

    finished = now_ms()
    return {
        "schema_version": "1.0",
        "upstream": "ai-costing-system",
        "project": "ai-costing-system",
        "trace_id": action.trace_id,
        "idempotency_key": action.idempotency_key,
        "status": status,
        "started_at_ms": started,
        "finished_at_ms": finished,
        "duration_ms": finished - started,
        "result": {"text": result_text, "json": result_json},
        "error": error,
    }


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
from .planner.services import bundle_template_service


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
            
            # 获取已发布的标准版本
            published_version = (
                db.query(models.ProductModelVersion)
                .filter(
                    models.ProductModelVersion.model_id == product.id,
                    models.ProductModelVersion.version_status == "published",
                    models.ProductModelVersion.is_archived.is_(False),
                )
                .order_by(models.ProductModelVersion.published_at.desc())
                .first()
            )
            
            materials_list = []
            processes_list = []
            version_info = None
            
            if published_version:
                version_info = {
                    "version_id": published_version.id,
                    "version_label": published_version.version_label,
                    "version_kind": published_version.version_kind,
                    "published_at": str(published_version.published_at) if published_version.published_at else None,
                }
                
                # 获取版本物料
                version_materials = (
                    db.query(models.ModelVersionMaterial)
                    .filter(
                        models.ModelVersionMaterial.version_id == published_version.id,
                        models.ModelVersionMaterial.is_archived.is_(False),
                    )
                    .order_by(models.ModelVersionMaterial.sequence_order)
                    .all()
                )
                for vm in version_materials:
                    materials_list.append({
                        "material_code": vm.material_code,
                        "material_name": vm.material_name,
                        "calculation_method": vm.calculation_method,
                        "base_quantity": float(vm.base_quantity) if vm.base_quantity else 0,
                        "loss_rate": float(vm.loss_rate) if vm.loss_rate else 0,
                        "unit_cost": float(vm.unit_cost) if vm.unit_cost else None,
                    })
                
                # 获取版本工序
                version_processes = (
                    db.query(models.ModelVersionProcess)
                    .filter(
                        models.ModelVersionProcess.version_id == published_version.id,
                        models.ModelVersionProcess.is_archived.is_(False),
                    )
                    .order_by(models.ModelVersionProcess.sequence_order)
                    .all()
                )
                for vp in version_processes:
                    proc = vp.process
                    processes_list.append({
                        "process_code": proc.process_code if proc else "",
                        "process_name": proc.process_name if proc else "",
                        "sequence_order": vp.sequence_order,
                    })
            
            # 构建文本摘要
            lines = [f"{m.model_code} {m.model_name} ({m.category or ''})"]
            if version_info:
                lines.append(f"已发布版本：{version_info.get('version_label') or '标准版'}")
            if materials_list:
                lines.append(f"物料清单（{len(materials_list)}项）：")
                for mat in materials_list[:5]:
                    lines.append(f"  - {mat['material_code'] or '?'} {mat['material_name'] or ''}")
                if len(materials_list) > 5:
                    lines.append(f"  ... +{len(materials_list) - 5} 项")
            if processes_list:
                lines.append(f"工序清单（{len(processes_list)}项）：")
                for proc in processes_list[:5]:
                    lines.append(f"  - {proc['process_name']}")
                if len(processes_list) > 5:
                    lines.append(f"  ... +{len(processes_list) - 5} 项")
            
            result_text = "\n".join(lines)
            result_json = {
                "product": m.dict(by_alias=True),
                "published_version": version_info,
                "materials": materials_list,
                "processes": processes_list,
            }

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

        elif name in ("bundle_template.search", "bundle_templates.search", "bundle_template.list"):
            q = (args.get("q") or args.get("search") or "").strip() or None
            page = int(args.get("page") or 1)
            page_size = int(args.get("page_size") or 20)
            page = max(1, page)
            page_size = max(1, min(200, page_size))
            category = (args.get("category") or "").strip() or None
            tag = (args.get("tag") or "").strip() or None
            include_archived = args.get("include_archived", False)

            filters = bundle_template_service.BundleTemplateFilters(
                search=q, category=category, tag=tag, include_archived=include_archived
            )
            total, items = bundle_template_service.list_templates(db, filters=filters, page=page, page_size=page_size)

            lines = [f"bundle_templates.search q={q or ''} total={total} page={page}"]
            items_out = []
            for t in items:
                comp_count = len(t.components_json or [])
                meta = t.metadata_json or {}
                lines.append(f"- {t.code} {t.name or ''} 组件数={comp_count}")
                items_out.append({
                    "id": str(t.id),
                    "code": t.code,
                    "name": t.name,
                    "component_count": comp_count,
                    "shared_trigger_text": str(meta.get("shared_trigger_text") or "").strip() or None,
                    "published_version_label": str(meta.get("published_version_label") or "").strip() or None,
                    "is_archived": bool(t.is_archived),
                })

            result_text = "\n".join(lines)
            result_json = {
                "q": q,
                "total": total,
                "page": page,
                "page_size": page_size,
                "items": items_out,
            }

        elif name in ("bundle_template.get", "bundle_templates.get", "bundle_template.by_code"):
            template_id = (args.get("template_id") or args.get("id") or "").strip()
            template_code = (args.get("template_code") or args.get("code") or "").strip()
            if not template_id and not template_code:
                raise HTTPException(status_code=400, detail="template_id or template_code is required")

            template = None
            if template_id:
                template = bundle_template_service.get_template(db, template_id, include_archived=True)
            if template is None and template_code:
                template = bundle_template_service.get_by_code(db, template_code)
            if template is None:
                raise HTTPException(status_code=404, detail="Bundle template not found")

            meta = template.metadata_json or {}
            components = template.components_json or []
            comp_summary = []
            for c in components[:5]:
                label = c.get("label") or ""
                w = c.get("width_mm", 0)
                h = c.get("height_mm", 0)
                qty = c.get("quantity", 1)
                comp_summary.append(f"{label or '组件'}({w}×{h})×{qty}")
            if len(components) > 5:
                comp_summary.append(f"+{len(components)-5}...")

            result_text = f"{template.code} {template.name or ''} 组件数={len(components)}"
            result_json = {
                "bundle_template": {
                    "id": str(template.id),
                    "code": template.code,
                    "name": template.name,
                    "component_count": len(components),
                    "components": components,
                    "components_summary": ", ".join(comp_summary),
                    "shared_trigger_text": str(meta.get("shared_trigger_text") or "").strip() or None,
                    "published_version_id": str(meta.get("published_version_id") or "").strip() or None,
                    "published_version_label": str(meta.get("published_version_label") or "").strip() or None,
                    "published_at": str(meta.get("published_at") or "").strip() or None,
                    "is_archived": bool(template.is_archived),
                }
            }

        elif name in ("semantic_search", "vector_search", "semantic.search"):
            # 语义搜索 - 调用向量搜索服务
            import httpx
            query = (args.get("query") or args.get("q") or "").strip()
            collection = (args.get("collection") or "materials").strip()
            top_k = int(args.get("top_k") or args.get("limit") or 10)
            top_k = max(1, min(50, top_k))

            if not query:
                raise HTTPException(status_code=400, detail="query is required")

            vector_search_url = os.getenv("VECTOR_SEARCH_URL", "http://127.0.0.1:8810")
            try:
                with httpx.Client(timeout=15.0) as client:
                    resp = client.get(
                        f"{vector_search_url}/api/v1/search",
                        params={"q": query, "collection": collection, "top_k": top_k},
                    )
                    if resp.status_code != 200:
                        raise HTTPException(status_code=502, detail=f"vector search failed: {resp.status_code}")
                    vec_data = resp.json()
            except httpx.RequestError as e:
                raise HTTPException(status_code=502, detail=f"vector search connection error: {e}")

            items = vec_data.get("items", [])
            total = vec_data.get("total", len(items))

            # 格式化结果
            lines = [f"semantic_search query={query} collection={collection} total={total}"]
            for it in items[:5]:
                meta = it.get("metadata", {})
                code = meta.get("material_code") or meta.get("model_code") or meta.get("module_code") or meta.get("code") or it.get("id", "")
                name_val = meta.get("material_name") or meta.get("model_name") or meta.get("module_name") or meta.get("name") or ""
                score = it.get("score", 0)
                lines.append(f"- {code} {name_val} (score={score:.2f})")
            result_text = "\n".join(lines)
            result_json = {
                "query": query,
                "collection": collection,
                "total": total,
                "items": items,
            }

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


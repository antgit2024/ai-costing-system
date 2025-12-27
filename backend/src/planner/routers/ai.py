from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ...database import get_db
from .. import models, schemas
from ..services import llm_text_service


router = APIRouter(prefix="/ai", tags=["ai"])


@router.get("/processes/corpus", response_model=schemas.AiProcessCorpusResponse)
def export_process_corpus(
    search: Optional[str] = Query(None, max_length=128),
    tag: Optional[str] = Query(None, max_length=64, description="Filter by process tag (metadata_json.process_tags contains tag)"),
    category: Optional[str] = Query(None, max_length=128),
    status: Optional[str] = Query(None, max_length=32),
    page: int = Query(1, ge=1),
    page_size: int = Query(200, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    # Keep it simple: corpus size is typically small. For large datasets, optimize with JSONB operators.
    q = db.query(models.Process).filter(models.Process.is_archived.is_(False))
    if search:
        pat = f"%{search.strip()}%"
        q = q.filter(models.Process.process_code.ilike(pat) | models.Process.process_name.ilike(pat))
    if category:
        q = q.filter(models.Process.category == category)
    if status:
        q = q.filter(models.Process.status == status)

    items = q.order_by(models.Process.updated_at.desc()).all()

    def _tags(meta: dict[str, Any]) -> list[str]:
        raw = meta.get("process_tags")
        if not isinstance(raw, list):
            return []
        return [str(x).strip() for x in raw if str(x).strip()]

    filtered: list[models.Process] = []
    for p in items:
        meta = dict(p.metadata_json or {})
        tags = _tags(meta)
        if tag and tag not in tags:
            continue
        filtered.append(p)

    total = len(filtered)
    start = (page - 1) * page_size
    end = start + page_size
    page_items = filtered[start:end]

    out: list[schemas.AiProcessCorpusItem] = []
    for p in page_items:
        meta = dict(p.metadata_json or {})
        tags = _tags(meta)
        ai_spec = meta.get("ai_spec")
        if not isinstance(ai_spec, dict):
            ai_spec = {}
        out.append(
            schemas.AiProcessCorpusItem(
                id=p.id,
                process_code=p.process_code,
                process_name=p.process_name,
                description=p.description,
                category=p.category,
                charging_mode=p.charging_mode,  # type: ignore[arg-type]
                unit_of_measure=p.unit_of_measure,
                status=p.status,
                tags=tags,
                ai_spec=ai_spec,
            )
        )

    return schemas.AiProcessCorpusResponse(total=total, items=out)


class GenerateModuleDescriptionRequest(BaseModel):
    module_name: str = Field("", max_length=255)
    category: str | None = Field(default=None, max_length=128)
    materials: list[dict[str, Any]] = Field(default_factory=list)
    steps: list[dict[str, Any]] = Field(default_factory=list)


class GenerateModuleDescriptionResponse(BaseModel):
    description: str
    provider: str


@router.post("/process-modules/describe", response_model=GenerateModuleDescriptionResponse)
def generate_process_module_description(payload: GenerateModuleDescriptionRequest):
    desc, provider = llm_text_service.generate_process_module_description(payload.dict())
    return GenerateModuleDescriptionResponse(description=desc, provider=provider)



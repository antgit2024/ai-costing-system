"""
GET /api/planner/binding-targets

为通用 <TargetPicker /> 组件提供候选搜索：
  - 一次返回标准模型（含变体编码 / 替换物料名）+ 套装模板（含 preset_selector）
  - 支持 kind 过滤（"model" / "bundle" / 不传=全部）
  - 支持 search 模糊匹配 code/name 以及变体/preset 文本

设计动机详见 services/binding_target_service.py。
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import schemas
from ..dependencies import get_db_session
from ..services import binding_target_service

router = APIRouter(prefix="/binding-targets", tags=["binding-targets"])


@router.get("", response_model=schemas.BindingTargetSearchResponse)
def search_binding_targets(
    search: Optional[str] = Query(None, max_length=128, description="模糊匹配 code/name/变体/preset"),
    kind: Optional[str] = Query(None, description="过滤：'model' | 'bundle'；不传则两类都返回"),
    limit: int = Query(50, ge=1, le=500, description="总返回上限；超过则 truncated=true"),
    db: Session = Depends(get_db_session),
):
    try:
        return binding_target_service.search_binding_targets(
            db, search=search, kind=kind, limit=limit
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

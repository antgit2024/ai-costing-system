from fastapi import Depends, Header, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..config import settings


class PaginationParams:
    def __init__(
        self,
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
    ):
        self.page = page
        self.page_size = page_size


def get_db_session(db: Session = Depends(get_db)) -> Session:
    return db


def require_admin_key(x_planner_admin_key: str | None = Header(default=None)) -> None:
    """
    Very lightweight admin guard for maintenance endpoints.
    - If PLANNER_ADMIN_KEY is not set, allow all (dev-friendly).
    - If set, require header X-PLANNER-ADMIN-KEY to match.
    """
    if not settings.planner_admin_key:
        return
    if not x_planner_admin_key or x_planner_admin_key != settings.planner_admin_key:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin key required")

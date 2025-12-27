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
    # 当前阶段按用户要求：先全开放（不做管理员校验）。
    # 后续如需恢复权限控制，再启用 PLANNER_ADMIN_KEY 校验逻辑。
    return

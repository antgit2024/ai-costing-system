from typing import Optional

from fastapi import Depends, Header, HTTPException, Query
from jose import JWTError
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..security.staff_jwt import StaffPayload, decode_staff_token


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


def require_admin_key(
    x_planner_admin_key: Optional[str] = Header(default=None, alias="X-PLANNER-ADMIN-KEY"),
) -> None:
    """服务账号守卫 · 用于 POD/executor 等服务间调用通道。

    - PLANNER_ADMIN_KEY 未配置时 (dev 环境) 直接放行;
    - 配置了就严格比对 · 不一致返回 403。

    注: 此函数在 COSTING-C1 之前被掏空成 `return` ·
    现已修复(派单红线 #2)。
    """
    if not settings.planner_admin_key:
        return
    if x_planner_admin_key != settings.planner_admin_key:
        raise HTTPException(status_code=403, detail="invalid_admin_key")


# 允许访问 ai-costing 全域 router 的角色白名单 · 见 COSTING-C1 §3.B
_ALLOWED_STAFF_ROLES = {"admin", "operator", "finance"}


def require_staff_role(
    authorization: Optional[str] = Header(default=None),
    x_planner_admin_key: Optional[str] = Header(default=None, alias="X-PLANNER-ADMIN-KEY"),
) -> Optional[StaffPayload]:
    """双轨认证守卫 (COSTING-C1) · 用于 ai-costing 业务 router 全域.

    路径 1: `Authorization: Bearer <staff_jwt>` (人 · 后台登录后)
            -> decode + role 白名单 · 通过则返回 StaffPayload
    路径 2: `X-PLANNER-ADMIN-KEY: <key>` (服务账号 · POD→ai-costing 算价等)
            -> 对比 settings.planner_admin_key · 通过则返回 None
    两条都没给 -> 401。
    """
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:].strip()
        try:
            payload = decode_staff_token(token)
        except JWTError as e:
            raise HTTPException(status_code=401, detail=f"invalid_token:{e}")
        except ValueError as e:
            raise HTTPException(status_code=401, detail=f"invalid_token:{e}")
        if payload.role not in _ALLOWED_STAFF_ROLES:
            raise HTTPException(
                status_code=403,
                detail=f"role_not_allowed:{payload.role}",
            )
        return payload

    if x_planner_admin_key:
        # dev-friendly: PLANNER_ADMIN_KEY 未配置时跟 require_admin_key 同行为放行 ·
        # prod 必须显式配 · CI/上线 checklist 要求强配。
        if not settings.planner_admin_key:
            return None
        if x_planner_admin_key != settings.planner_admin_key:
            raise HTTPException(status_code=403, detail="invalid_admin_key")
        return None

    raise HTTPException(status_code=401, detail="missing_authorization_header")

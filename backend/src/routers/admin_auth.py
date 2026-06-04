"""ai-costing 员工登录 · 代理转发到 POD `/admin/staff/login` (POD 是 IdP) ·
COSTING-C1 §3.D-3 验收必经。

设计要点:
- ai-costing 不存任何明文密码 / 不持有 staff_users 表;
- 登录请求透传到 POD 后端 · 拿到 token 直接回前端;
- /me 端点从 JWT decode 出身份 · 不查 DB · 用于前端 AuthGuard。
"""
from __future__ import annotations

from typing import Any, Dict

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..config import settings
from ..planner.dependencies import require_staff_role
from ..security.staff_jwt import StaffPayload


router = APIRouter(prefix="/admin/auth", tags=["admin-auth"])


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=128)


@router.post("/login")
async def login(req: LoginRequest) -> Dict[str, Any]:
    """代理转发到 POD · 不存任何明文密码。

    成功响应直接透传 POD 的 `LoginResponse {access_token, token_type, staff: {...}}` ·
    前端拿到后自行存 access_token + staff 入 zustand。
    """
    upstream = f"{settings.pod_login_proxy_url.rstrip('/')}{settings.pod_login_path}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                upstream,
                json={"username": req.username, "password": req.password},
            )
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=502,
            detail=f"pod_login_proxy_unreachable:{e}",
        )

    if resp.status_code != 200:
        try:
            detail = resp.json().get("detail", "login_failed")
        except Exception:
            detail = resp.text or "login_failed"
        raise HTTPException(status_code=resp.status_code, detail=detail)
    return resp.json()


@router.get("/me")
def me(payload: StaffPayload = Depends(require_staff_role)) -> Dict[str, str]:
    """当前员工身份(从 JWT decode · 不查 DB)。
    服务账号路径(payload=None) 不能访问 /me · 只允许人调用。
    """
    if payload is None:
        raise HTTPException(status_code=401, detail="not_authenticated_human")
    return {
        "staff_id": payload.sub,
        "username": payload.username,
        "role": payload.role,
    }

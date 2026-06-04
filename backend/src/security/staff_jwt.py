"""与 POD 平台共享的 staff JWT decode 逻辑(只验 · 不发 token)。

设计要点(见 DOC/agents/handoffs/2026-05-04-COSTING-C1-*):
- POD 平台是唯一 IdP · ai-costing 复用 POD 颁发的 JWT。
- 共享 POD_JWT_SECRET_KEY(env 同步)· 本地 decode · 0 网络开销。
- ai-costing 不持有 staff_users 表 · 不查 DB · 不验账号是否存在(信任 POD)。
- payload.typ 必须等于 STAFF_TOKEN_TYP("staff") · 防止其他系统 token 误用。
"""
from __future__ import annotations

from typing import Optional

from jose import jwt
from pydantic import BaseModel

from ..config import settings


STAFF_TOKEN_TYP = "staff"


class StaffPayload(BaseModel):
    """与 POD `pod-design-platform/backend/src/services/staff_auth_service.StaffPayload` 字段对齐."""

    sub: str        # staff_id (POD staff_users.id)
    role: str       # admin / operator / finance / cs / designer
    username: str   # 显示名 / 登录名
    typ: str = STAFF_TOKEN_TYP


def decode_staff_token(token: str) -> StaffPayload:
    """与 POD `decode_staff_token` 等价 · 但不查 DB(没有 staff_users 表).

    任何 decode 失败(签名错 / 过期 / typ 不对 / 字段缺失) 都会抛异常 ·
    由调用方(`require_staff_role`)统一翻 401。
    """
    payload = jwt.decode(
        token,
        settings.pod_jwt_secret_key,
        algorithms=[settings.pod_jwt_algorithm],
    )
    if payload.get("typ") != STAFF_TOKEN_TYP:
        raise ValueError(f"invalid token type: expected '{STAFF_TOKEN_TYP}', got '{payload.get('typ')}'")
    if not payload.get("sub"):
        raise ValueError("token missing staff identity (sub)")
    return StaffPayload(**payload)

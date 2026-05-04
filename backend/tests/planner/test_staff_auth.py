"""COSTING-C1 · staff JWT decode + require_staff_role 双轨认证守卫单测."""
from __future__ import annotations

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from jose import jwt as jose_jwt

from src.config import settings
from src.planner.dependencies import require_staff_role
from src.security.staff_jwt import (
    STAFF_TOKEN_TYP,
    StaffPayload,
    decode_staff_token,
)


@pytest.fixture
def secret() -> str:
    return settings.pod_jwt_secret_key


def _make_token(secret: str, **overrides) -> str:
    payload = {
        "sub": "staff-1",
        "role": "admin",
        "username": "admin1",
        "typ": STAFF_TOKEN_TYP,
        **overrides,
    }
    return jose_jwt.encode(payload, secret, algorithm=settings.pod_jwt_algorithm)


# ============ decode_staff_token ============

class TestDecodeStaffToken:
    def test_decode_valid_token(self, secret):
        token = _make_token(secret)
        payload = decode_staff_token(token)
        assert isinstance(payload, StaffPayload)
        assert payload.sub == "staff-1"
        assert payload.role == "admin"
        assert payload.username == "admin1"
        assert payload.typ == STAFF_TOKEN_TYP

    def test_decode_rejects_wrong_typ_factory_staff(self, secret):
        """红线 #3 · POD `staff` token 与其他系统 token 严格隔离 ·
        即使签名密钥相同 · typ 不对也必须拒收。
        """
        token = _make_token(secret, typ="factory_staff")
        with pytest.raises(ValueError, match="invalid token type"):
            decode_staff_token(token)

    def test_decode_rejects_missing_typ(self, secret):
        token = jose_jwt.encode(
            {"sub": "x", "role": "admin", "username": "x"},
            secret,
            algorithm=settings.pod_jwt_algorithm,
        )
        with pytest.raises(ValueError, match="invalid token type"):
            decode_staff_token(token)

    def test_decode_rejects_missing_sub(self, secret):
        token = jose_jwt.encode(
            {"role": "admin", "username": "x", "typ": STAFF_TOKEN_TYP},
            secret,
            algorithm=settings.pod_jwt_algorithm,
        )
        with pytest.raises(ValueError, match="missing staff identity"):
            decode_staff_token(token)

    def test_decode_rejects_bad_signature(self, secret):
        from jose import JWTError

        token = _make_token("wrong-secret")
        with pytest.raises(JWTError):
            decode_staff_token(token)


# ============ require_staff_role · 双轨认证 ============

@pytest.fixture
def staff_app():
    """构造一个最小 FastAPI · 端点 require require_staff_role · 用于行为测试."""
    from fastapi import Depends

    app = FastAPI()

    @app.get("/protected")
    def protected(payload=Depends(require_staff_role)):
        return {"sub": payload.sub if payload else None}

    return TestClient(app)


class TestRequireStaffRole:
    def test_no_credentials_returns_401(self, staff_app):
        resp = staff_app.get("/protected")
        assert resp.status_code == 401
        assert "missing_authorization_header" in resp.json()["detail"]

    def test_valid_admin_bearer_passes(self, staff_app, secret):
        token = _make_token(secret, role="admin")
        resp = staff_app.get("/protected", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["sub"] == "staff-1"

    def test_valid_operator_passes(self, staff_app, secret):
        token = _make_token(secret, role="operator")
        resp = staff_app.get("/protected", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_valid_finance_passes(self, staff_app, secret):
        token = _make_token(secret, role="finance")
        resp = staff_app.get("/protected", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_role_cs_rejected_403(self, staff_app, secret):
        token = _make_token(secret, role="cs")
        resp = staff_app.get("/protected", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 403
        assert "role_not_allowed:cs" in resp.json()["detail"]

    def test_role_designer_rejected_403(self, staff_app, secret):
        token = _make_token(secret, role="designer")
        resp = staff_app.get("/protected", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 403

    def test_invalid_signature_returns_401(self, staff_app):
        token = _make_token("wrong-secret-key")
        resp = staff_app.get("/protected", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401
        assert "invalid_token" in resp.json()["detail"]

    def test_wrong_typ_returns_401(self, staff_app, secret):
        """红线 #3 · ai-costing 拒收非 staff 类型 token."""
        token = _make_token(secret, typ="factory_staff")
        resp = staff_app.get("/protected", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401
        assert "invalid_token" in resp.json()["detail"]

    def test_admin_key_path_dev_empty_passes(self, staff_app):
        """dev 模式 settings.planner_admin_key 为空 · 任何 X-PLANNER-ADMIN-KEY 都放行."""
        assert not settings.planner_admin_key  # dev 默认空
        resp = staff_app.get("/protected", headers={"X-PLANNER-ADMIN-KEY": "anything"})
        assert resp.status_code == 200
        assert resp.json()["sub"] is None  # 服务账号 · 无 staff 身份

    def test_admin_key_strict_when_configured(self, staff_app, monkeypatch):
        """prod 模式 (planner_admin_key 已配) · 错 key 必须 403."""
        monkeypatch.setattr(settings, "planner_admin_key", "real-key-xyz")
        resp = staff_app.get("/protected", headers={"X-PLANNER-ADMIN-KEY": "WRONG"})
        assert resp.status_code == 403
        assert "invalid_admin_key" in resp.json()["detail"]

    def test_admin_key_strict_correct_passes(self, staff_app, monkeypatch):
        monkeypatch.setattr(settings, "planner_admin_key", "real-key-xyz")
        resp = staff_app.get("/protected", headers={"X-PLANNER-ADMIN-KEY": "real-key-xyz"})
        assert resp.status_code == 200
        assert resp.json()["sub"] is None

    def test_bearer_priority_over_admin_key(self, staff_app, secret, monkeypatch):
        """同时给两个 header · Bearer 优先 · 错 admin_key 也通."""
        monkeypatch.setattr(settings, "planner_admin_key", "real-key-xyz")
        token = _make_token(secret, role="admin")
        resp = staff_app.get(
            "/protected",
            headers={
                "Authorization": f"Bearer {token}",
                "X-PLANNER-ADMIN-KEY": "WRONG",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["sub"] == "staff-1"


# ============ /admin/auth/me 端点行为 ============

class TestAdminAuthMe:
    def test_me_with_staff_token(self, secret):
        from src.main import app

        token = _make_token(secret, sub="me-1", role="admin", username="alice")
        with TestClient(app) as client:
            resp = client.get("/admin/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json() == {"staff_id": "me-1", "username": "alice", "role": "admin"}

    def test_me_rejects_service_account(self):
        """/me 不允许服务账号(payload=None) · 必须是人."""
        from src.main import app

        # 先临时覆写让 admin_key 路径放行(dev 默认空 key 已经放行)
        with TestClient(app) as client:
            resp = client.get("/admin/auth/me", headers={"X-PLANNER-ADMIN-KEY": "x"})
        assert resp.status_code == 401
        assert "not_authenticated_human" in resp.json()["detail"]

    def test_me_rejects_unauthenticated(self):
        from src.main import app

        with TestClient(app) as client:
            resp = client.get("/admin/auth/me")
        assert resp.status_code == 401

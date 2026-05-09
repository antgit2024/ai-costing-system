"""Wire-level contract tests for the Jackyun open-platform client.

These tests pin the *public* request format against the documented
「外部系统对接开放平台」 spec (snapshot 2026-05) so that future refactors of
``client.py`` can't silently break the wire format. Earlier mapper/route
tests stub out ``JackyunClient.call`` and therefore wouldn't catch a regression
in field names, signing, or response classification.

Spec recap (do NOT relax without updating the docstring AND .env):
- Gateway URL: https://open.jackyun.com/open/openapi/do
- Public params (form-urlencoded POST): method / appkey / version /
  contenttype / timestamp / bizcontent / sign
- Sign: ``md5( (secret + sorted(k+v) + secret).toLowerCase() )``
- Success envelope: ``code: 0`` (NOT 200), ``subCode`` absent or all-zero,
  payload under ``result.data``.
- ``0130020310 = 未订阅此API`` -> auth-class error, not retryable.
- ``0859999999 = 上游限流`` -> retryable business error.
"""

from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Tuple

import pytest

from src.integrations.base.errors import (
    IntegrationAuthError,
    IntegrationBusinessError,
)
from src.integrations.jackyun.client import (
    JackyunClient,
    JackyunSigner,
    _BUSINESS_OK_SUB_CODES,
)


APP_KEY = "22258171"
APP_SECRET = "TEST_SECRET_NOT_REAL"


def _expected_md5_signature(params: Dict[str, Any], secret: str) -> str:
    pairs: List[str] = []
    for key in sorted(params):
        if key in ("sign", "token", "contextid"):
            continue
        value = params[key]
        if value is None:
            continue
        pairs.append(f"{key}{value}")
    raw = f"{secret}{''.join(pairs)}{secret}".lower()
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Signer / public-params shape
# ---------------------------------------------------------------------------


class TestSignerShape:
    def setup_method(self) -> None:
        self.signer = JackyunSigner(
            app_key=APP_KEY, app_secret=APP_SECRET, version="1.0"
        )

    def test_signer_emits_documented_public_param_keys(self) -> None:
        public = {"method": "wms.order.query-info.page.v2"}
        biz = {"pageIndex": 1, "pageSize": 5}
        signed, headers = self.signer.sign(public_params=public, biz_content=biz)

        # Wire field names MUST match the docs verbatim — spotted bugs in the
        # past where ``app_key`` / ``biz_content`` / ``v`` / ``format`` were
        # used instead, all of which the gateway rejects.
        for required in ("method", "appkey", "version", "contenttype",
                         "timestamp", "bizcontent", "sign"):
            assert required in signed, f"missing required public param: {required}"

        for forbidden in ("app_key", "biz_content", "v", "format", "sign_method"):
            assert forbidden not in signed, (
                f"public param '{forbidden}' must NOT be sent — wrong dialect"
            )

        # Signing returns no extra HTTP headers (auth lives in form body).
        assert headers == {}

    def test_timestamp_is_shanghai_local_string_no_offset(self) -> None:
        signed, _ = self.signer.sign(
            public_params={"method": "wms.order.query-info.page.v2"},
            biz_content={},
        )
        ts = signed["timestamp"]
        # ``YYYY-MM-DD HH:MM:SS`` exactly — no ``T``, no ``Z``, no ``+08:00``.
        assert len(ts) == 19
        assert ts[4] == "-" and ts[7] == "-" and ts[10] == " "
        assert ts[13] == ":" and ts[16] == ":"

    def test_bizcontent_is_serialized_json_string(self) -> None:
        signed, _ = self.signer.sign(
            public_params={"method": "wms.order.query-info.page.v2"},
            biz_content={"pageIndex": 1, "pageSize": 5},
        )
        # Form-urlencoded body needs strings, not nested dicts; if a future
        # change forwards a dict, ``requests`` would silently re-encode it
        # in a way that breaks signing.
        assert isinstance(signed["bizcontent"], str)
        assert "pageIndex" in signed["bizcontent"]


# ---------------------------------------------------------------------------
# Sign computation
# ---------------------------------------------------------------------------


class TestSigning:
    def setup_method(self) -> None:
        self.signer = JackyunSigner(
            app_key=APP_KEY, app_secret=APP_SECRET, version="1.0"
        )

    def test_sign_matches_md5_of_lowercased_concatenation(self) -> None:
        public = {"method": "wms.order.query-info.page.v2"}
        biz = {"pageIndex": 1, "pageSize": 5}
        signed, _ = self.signer.sign(public_params=public, biz_content=biz)

        expected = _expected_md5_signature(signed, APP_SECRET)
        assert signed["sign"] == expected
        # MD5 hex digest is 32 lowercase chars.
        assert len(signed["sign"]) == 32
        assert signed["sign"] == signed["sign"].lower()

    def test_sign_excludes_sign_token_and_contextid(self) -> None:
        # If signer ever included these in the pre-image, requests with a
        # token would fail signature validation upstream.
        signer = self.signer
        baseline = signer._compute_sign({  # noqa: SLF001 — pin the algorithm
            "method": "wms.order.query-info.page.v2",
            "appkey": APP_KEY,
            "version": "1.0",
            "contenttype": "json",
            "timestamp": "2026-05-06 12:00:00",
            "bizcontent": "{}",
        })
        with_extras = signer._compute_sign({  # noqa: SLF001
            "method": "wms.order.query-info.page.v2",
            "appkey": APP_KEY,
            "version": "1.0",
            "contenttype": "json",
            "timestamp": "2026-05-06 12:00:00",
            "bizcontent": "{}",
            "sign": "deadbeef",
            "token": "tok_abc",
            "contextid": "ctx_xyz",
        })
        assert baseline == with_extras


# ---------------------------------------------------------------------------
# Response normalization (the ``code:0 vs 200`` and subCode rules)
# ---------------------------------------------------------------------------


class TestParseResponse:
    def setup_method(self) -> None:
        self.client = JackyunClient(
            app_key=APP_KEY, app_secret=APP_SECRET,
            base_url="https://open.jackyun.com/open/openapi/do",
            version="1.0",
        )

    def test_success_when_code_zero_and_subcode_absent(self) -> None:
        body = {
            "code": 0,
            "msg": "ok",
            "result": {"contextId": "ctx-1", "data": [{"id": "S1"}]},
        }
        resp = self.client.parse_response(http_status=200, body=body)
        assert resp.success is True
        assert resp.biz_code == "0"
        assert resp.biz_sub_code is None
        assert resp.context_id == "ctx-1"
        assert resp.data == [{"id": "S1"}]

    def test_success_when_subcode_is_all_zero(self) -> None:
        for sub in sorted(_BUSINESS_OK_SUB_CODES):
            body = {"code": 0, "subCode": sub, "result": {"data": []}}
            resp = self.client.parse_response(http_status=200, body=body)
            assert resp.success is True, f"subCode={sub} should count as ok"

    def test_failure_when_code_zero_but_subcode_nonzero(self) -> None:
        body = {
            "code": 0,
            "msg": "appKey=22258171,method=...,未查询到应用或应用未订阅此API",
            "subCode": "0130020310",
            "result": {"data": None, "contextId": "ctx-2"},
        }
        resp = self.client.parse_response(http_status=200, body=body)
        # The hard-won lesson: code=0 alone does NOT mean success — subCode is
        # the real business signal.
        assert resp.success is False
        assert resp.biz_code == "0"
        assert resp.biz_sub_code == "0130020310"
        assert resp.context_id == "ctx-2"

    def test_failure_when_http_non_200(self) -> None:
        resp = self.client.parse_response(http_status=500, body={"code": 0})
        assert resp.success is False

    def test_legacy_code_200_still_treated_as_framework_ok(self) -> None:
        # Some older Jackyun methods returned ``"code": 200`` instead of 0.
        # Keep both accepted so we don't accidentally regress that surface.
        body = {"code": 200, "result": {"data": []}}
        resp = self.client.parse_response(http_status=200, body=body)
        assert resp.success is True


# ---------------------------------------------------------------------------
# Error classification & retry policy
# ---------------------------------------------------------------------------


class TestErrorClassification:
    def setup_method(self) -> None:
        self.client = JackyunClient(
            app_key=APP_KEY, app_secret=APP_SECRET,
            base_url="https://open.jackyun.com/open/openapi/do",
            version="1.0",
        )

    def _resp(self, *, sub: str, msg: str) -> Any:
        body = {"code": 0, "msg": msg, "subCode": sub, "result": {"data": None}}
        return self.client.parse_response(http_status=200, body=body)

    @pytest.mark.parametrize("sub_code", [
        "0858030801",  # sign failed
        "0858030802",  # appkey unknown
        "0858030803",  # token invalid/expired
        "0130020310",  # 未订阅 API — operator action required
    ])
    def test_auth_codes_are_classified_as_auth_error(self, sub_code: str) -> None:
        resp = self._resp(sub=sub_code, msg="upstream rejected")
        err = self.client._classify_error("wms.order.query-info.page.v2", resp)  # noqa: SLF001
        assert isinstance(err, IntegrationAuthError)
        assert err.retryable is False
        # Sub-code is included in the surfaced message so dead-letter rows are
        # immediately actionable in the UI.
        assert sub_code in err.message

    def test_unknown_business_code_is_not_retryable_by_default(self) -> None:
        resp = self._resp(sub="0123456789", msg="参数无效")
        assert self.client.is_retryable_business(resp) is False
        err = self.client._classify_error("wms.order.query-info.page.v2", resp)  # noqa: SLF001
        assert isinstance(err, IntegrationBusinessError)
        assert err.retryable is False

    def test_throttle_code_is_retryable(self) -> None:
        resp = self._resp(sub="0859999999", msg="请稍后重试")
        assert self.client.is_retryable_business(resp) is True

    def test_message_with_chinese_auth_keyword_is_classified_as_auth(self) -> None:
        # Defense in depth: even if the upstream returns an unfamiliar
        # subCode, a clearly auth-flavored Chinese message still routes to
        # ``IntegrationAuthError`` so we don't put it on a retry loop.
        resp = self._resp(sub="9999999999", msg="认证失败,签名不正确")
        err = self.client._classify_error("wms.order.query-info.page.v2", resp)  # noqa: SLF001
        assert isinstance(err, IntegrationAuthError)


# ---------------------------------------------------------------------------
# End-to-end signing-via-call (no real network)
# ---------------------------------------------------------------------------


class _FakeResp:
    def __init__(self, status: int, body: Dict[str, Any]) -> None:
        self.status_code = status
        self._body = body
        self.text = ""
        self.headers = {"Content-Type": "application/json"}

    def json(self) -> Dict[str, Any]:
        return self._body


class _FakeSession:
    def __init__(self, body: Dict[str, Any]) -> None:
        self._body = body
        self.calls: List[Tuple[str, Dict[str, Any]]] = []

    def post(self, url: str, *, data: Dict[str, Any], headers: Dict[str, str], timeout: float) -> _FakeResp:  # noqa: ARG002
        self.calls.append((url, dict(data)))
        return _FakeResp(200, self._body)


def test_call_posts_to_configured_gateway_with_signed_form_body() -> None:
    """End-to-end ``call()`` must hit the configured URL and ship a fully
    signed form body that matches the documented spec, not whatever defaults
    the base class might cobble together.
    """

    session = _FakeSession({"code": 0, "result": {"contextId": "ctx-e2e", "data": []}})
    client = JackyunClient(
        app_key=APP_KEY, app_secret=APP_SECRET,
        base_url="https://open.jackyun.com/open/openapi/do",
        version="1.0",
        max_retries=0,
    )
    # JackyunClient doesn't yet expose ``session`` in its own ctor; injecting
    # via the inherited attribute keeps the test focused on wire format
    # without forcing a signature change just for tests.
    client._session = session  # type: ignore[assignment]  # noqa: SLF001

    resp = client.call(
        "wms.order.query-info.page.v2",
        {"pageIndex": 1, "pageSize": 1,
         "startModifyTime": "2026-05-06 00:00:00",
         "endModifyTime": "2026-05-06 23:59:59"},
    )
    assert resp.success is True
    assert resp.context_id == "ctx-e2e"

    assert len(session.calls) == 1
    url, body = session.calls[0]
    assert url == "https://open.jackyun.com/open/openapi/do"
    assert body["method"] == "wms.order.query-info.page.v2"
    assert body["appkey"] == APP_KEY
    assert body["version"] == "1.0"
    assert body["contenttype"] == "json"
    assert "bizcontent" in body and "pageIndex" in body["bizcontent"]
    assert body["sign"] == _expected_md5_signature(body, APP_SECRET)
    # And the legacy spelling absolutely must not show up anywhere.
    assert "biz_content" not in body
    assert "app_key" not in body

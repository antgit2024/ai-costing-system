"""Jackyun open API HTTP client + signer.

Gateway & contract (per official docs, 「外部系统对接开放平台」, 2026-05):
- 线上环境 URL: ``https://open.jackyun.com/open/openapi/do``
- Public params (form-urlencoded POST, all required unless marked):
    method / appkey / version / contenttype / timestamp / bizcontent / sign
    contextid (optional, NOT signed) / token (optional, NOT signed)
- Signing recipe (matches the Java SDK ``buildJackyunSign``):
    1. Drop ``sign`` / ``token`` / ``contextid`` and any None values.
    2. Sort the remaining keys lexicographically.
    3. Concatenate as ``key1value1key2value2…`` (no separators).
    4. Prepend AND append the app secret.
    5. **Lower-case** the entire string, then MD5, take the 32-char hex digest.
- Response envelope:
    {"code": 0, "msg": "...", "subCode": "0000000000",
     "result": {"contextId": "...", "data": ...}}
    framework status lives in ``code`` (0 == ok, NOT 200).
    business status lives in ``subCode`` (zero-only ⇒ ok; any other code ⇒
    business failure, surfaced in ``msg``).

If a tenant's signing or envelope differs in the future, override only
``JackyunSigner._compute_sign`` / ``JackyunClient.parse_response``; the
generic ``BaseClient`` stays untouched.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

from ...config import settings
from ..base.client import BaseClient, ClientResponse
from ..base.errors import IntegrationAuthError, IntegrationBusinessError
from ..base.signer import Signer


_SHANGHAI_TZ = timezone(timedelta(hours=8))


# Treat any of these as "framework/business OK" — anything else in subCode is
# a real business failure.
#
# - "0" / "0000000000" / "00000000": classic Jackyun WMS-API success codes
# - "200": OMS-API namespace (e.g. omsapi-business.refund.listrefund) returns
#   subCode="200" on success instead of zero. Discovered 2026-05-12 while
#   wiring up refund sync; without this entry the parse_response below would
#   classify a HTTP-200/code-200/subCode-200 response as a business failure
#   and drop a real success into the dead-letter queue.
# - "0030000004": ERP namespace (e.g. erp.storage.goodslist) returns
#   subCode="0030000004" with msg="操作成功" on success. Discovered 2026-05-16
#   while wiring up goods master sync.
_BUSINESS_OK_SUB_CODES = {"0", "0000000000", "00000000", "200", "0030000004"}


# Sub-codes that indicate the *caller* (key/secret/token/subscription)
# is the problem and MUST NOT be auto-retried — surface them as auth errors
# so operators get a clear, actionable signal in the dead-letter queue.
_AUTH_SUB_CODES = {
    # 0858030801 / 0858030802 / 0858030803 are the documented sign/appkey/token
    # validation failures from Jackyun's gateway.
    "0858030801",
    "0858030802",
    "0858030803",
    # 0130020310 = "未查询到应用或应用未订阅此API" — needs human action in the
    # 吉客云开放平台 → 应用管理 to subscribe the relevant API.
    "0130020310",
}


# Sub-codes that ARE safe to retry (e.g. transient throttling). Keep narrow.
_RETRYABLE_SUB_CODES = {
    "0859999999",  # generic upstream throttle / temporarily unavailable
}


class JackyunSigner(Signer):
    def __init__(self, *, app_key: str, app_secret: str, version: str) -> None:
        if not app_key or not app_secret:
            raise ValueError("Jackyun signer requires both app_key and app_secret")
        self.app_key = app_key
        self.app_secret = app_secret
        self.version = version

    def sign(
        self,
        *,
        public_params: Dict[str, Any],
        biz_content: Any,
    ) -> Tuple[Dict[str, Any], Dict[str, str]]:
        params: Dict[str, Any] = dict(public_params)
        params.setdefault("appkey", self.app_key)
        params.setdefault("version", self.version)
        params.setdefault("contenttype", "json")
        params.setdefault("timestamp", _format_timestamp(datetime.now(_SHANGHAI_TZ)))

        params["bizcontent"] = _normalize_biz_content(biz_content)

        params["sign"] = self._compute_sign(params)
        return params, {}

    def _compute_sign(self, params: Dict[str, Any]) -> str:
        signing_pairs = []
        for key in sorted(params.keys()):
            # ``sign`` is the output; ``token``/``contextid`` are documented
            # to be excluded from the signing string.
            if key in ("sign", "token", "contextid"):
                continue
            value = params[key]
            if value is None:
                continue
            signing_pairs.append(f"{key}{value}")
        joined = "".join(signing_pairs)
        # Per the Java SDK: ``md5( (secret + ... + secret).toLowerCase() )``
        raw = f"{self.app_secret}{joined}{self.app_secret}".lower()
        return hashlib.md5(raw.encode("utf-8")).hexdigest()  # noqa: S324 - per upstream spec


class JackyunClient(BaseClient):
    source_system = "jackyun"

    def __init__(
        self,
        *,
        app_key: str,
        app_secret: str,
        base_url: Optional[str] = None,
        version: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        max_retries: Optional[int] = None,
    ) -> None:
        self.base_url = base_url or settings.jackyun_api_base_url
        signer = JackyunSigner(
            app_key=app_key,
            app_secret=app_secret,
            version=version or settings.jackyun_api_version,
        )
        super().__init__(
            signer=signer,
            timeout_seconds=timeout_seconds or settings.jackyun_timeout_seconds,
            max_retries=max_retries if max_retries is not None else settings.jackyun_max_retries,
        )

    def build_public_params(self, api_method: str) -> Dict[str, Any]:
        return {"method": api_method}

    def parse_response(self, *, http_status: int, body: Dict[str, Any]) -> ClientResponse:
        result = body.get("result") if isinstance(body, dict) else None
        context_id: Optional[str] = None
        data: Any = result
        if isinstance(result, dict):
            context_id = result.get("contextId") or result.get("contextid")
            data = result.get("data", result)
            # OMS-API namespace (omsapi-business.*) returns ``result.data`` as
            # a JSON-encoded STRING rather than a nested object. Decode it
            # once here so all downstream callers see uniform dict/list
            # shapes. Discovered 2026-05-12 with omsapi-business.refund.listrefund.
            if isinstance(data, str):
                stripped = data.strip()
                if stripped[:1] in ("{", "["):
                    try:
                        data = json.loads(stripped)
                    except (ValueError, TypeError):
                        # Not valid JSON; leave as-is so mappers can decide.
                        pass

        biz_code = body.get("code") if isinstance(body, dict) else None
        sub_code_raw = body.get("subCode") if isinstance(body, dict) else None
        sub_code: Optional[str] = (
            str(sub_code_raw) if sub_code_raw not in (None, "") else None
        )

        # Framework-level success: HTTP 200 + body.code in {0, 200}.
        # Some legacy methods also use 200 for "ok"; we accept both.
        framework_ok = http_status == 200 and biz_code in (0, "0", 200, "200")
        # Business-level success: subCode missing OR explicitly all-zero.
        business_ok = (sub_code is None) or (sub_code in _BUSINESS_OK_SUB_CODES)

        return ClientResponse(
            success=framework_ok and business_ok,
            biz_code=str(biz_code) if biz_code is not None else None,
            biz_sub_code=sub_code,
            message=str(body.get("msg")) if isinstance(body, dict) and body.get("msg") is not None else None,
            data=data,
            raw=body if isinstance(body, dict) else {"_raw": body},
            http_status=http_status,
            context_id=context_id,
        )

    def is_retryable_business(self, response: ClientResponse) -> bool:
        sub = response.biz_sub_code or ""
        # Default-deny on retries; only the explicitly safe codes loop again.
        # Avoids hammering the upstream for permission/data errors.
        return sub in _RETRYABLE_SUB_CODES

    def _classify_error(self, api_method: str, response: ClientResponse):
        sub = response.biz_sub_code or ""
        # Surface subCode in the message so dead-letter rows are self-explanatory.
        base_msg = response.message or "jackyun upstream error"
        msg = f"[{sub or '?'}] {base_msg}" if sub else base_msg
        ctx = {
            "source_system": self.source_system,
            "api_method": api_method,
            "biz_code": response.biz_code,
            "biz_sub_code": response.biz_sub_code,
            "http_status": response.http_status,
            "context_id": response.context_id,
        }
        if sub in _AUTH_SUB_CODES or "认证" in base_msg or "未订阅" in base_msg:
            return IntegrationAuthError(msg, **ctx)
        return IntegrationBusinessError(msg, **ctx)


def _format_timestamp(dt: datetime) -> str:
    # Jackyun timestamps are documented as ``YYYY-MM-DD HH:MM:SS`` in
    # Beijing/Shanghai local time (no timezone suffix). Sending UTC will
    # silently drift signature freshness checks, so always normalize to +08.
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_SHANGHAI_TZ)
    return dt.astimezone(_SHANGHAI_TZ).strftime("%Y-%m-%d %H:%M:%S")


def _normalize_biz_content(biz_content: Any) -> str:
    if biz_content is None:
        return "{}"
    if isinstance(biz_content, str):
        return biz_content
    return json.dumps(biz_content, ensure_ascii=False, sort_keys=True)


def build_default_client() -> JackyunClient:
    """Construct a client from environment-backed settings.

    Raises ``RuntimeError`` if ``JACKYUN_APP_KEY``/``JACKYUN_APP_SECRET`` are
    not configured. Callers can catch this to short-circuit when running in
    dev/CI without real credentials.
    """

    if not settings.jackyun_app_key or not settings.jackyun_app_secret:
        raise RuntimeError(
            "JACKYUN_APP_KEY / JACKYUN_APP_SECRET not configured (set in .env, never commit)"
        )
    return JackyunClient(
        app_key=settings.jackyun_app_key,
        app_secret=settings.jackyun_app_secret,
    )

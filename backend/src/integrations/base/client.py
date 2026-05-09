"""Shared HTTP client base for all upstream integrations.

Goals:
- Single place to enforce timeout / retry / log every call into
  ``integration_api_call_logs``.
- Vendor subclasses only declare ``base_url`` / ``signer`` / ``method_router``.
- Stays sync (uses ``requests``) to match the rest of this codebase
  (Yida client, dingtalk client, etc).
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

import requests
from sqlalchemy.orm import Session

from .errors import (
    IntegrationAuthError,
    IntegrationBusinessError,
    IntegrationError,
    IntegrationTransportError,
)
from .signer import NullSigner, Signer

DEFAULT_TIMEOUT_SECONDS = 15.0
DEFAULT_MAX_RETRIES = 2
DEFAULT_RETRY_BACKOFF_SECONDS = 0.5


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _truncate_for_log(value: Any, *, limit: int = 8000) -> Any:
    """Avoid blowing up call_logs JSON columns on huge payloads."""

    try:
        text = json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        text = str(value)
    if len(text) <= limit:
        return value
    return {"_truncated": True, "preview": text[:limit]}


@dataclass
class ClientResponse:
    """Normalized response across vendors."""

    success: bool
    biz_code: Optional[str]
    biz_sub_code: Optional[str]
    message: Optional[str]
    data: Any
    raw: Dict[str, Any]
    http_status: int
    context_id: Optional[str] = None
    duration_ms: int = 0
    request_payload: Dict[str, Any] = field(default_factory=dict)


class BaseClient:
    """Common scaffolding for vendor HTTP clients.

    Subclass this and override:
    - ``source_system`` (str)
    - ``base_url`` (str)
    - ``signer`` (Signer)
    - ``parse_response`` (vendor-specific normalization)
    """

    source_system: str = ""
    base_url: str = ""
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    max_retries: int = DEFAULT_MAX_RETRIES
    retry_backoff_seconds: float = DEFAULT_RETRY_BACKOFF_SECONDS

    def __init__(
        self,
        *,
        signer: Optional[Signer] = None,
        timeout_seconds: Optional[float] = None,
        max_retries: Optional[int] = None,
        retry_backoff_seconds: Optional[float] = None,
        session: Optional[requests.Session] = None,
        log_writer: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> None:
        self.signer: Signer = signer or NullSigner()
        if timeout_seconds is not None:
            self.timeout_seconds = timeout_seconds
        if max_retries is not None:
            self.max_retries = max_retries
        if retry_backoff_seconds is not None:
            self.retry_backoff_seconds = retry_backoff_seconds
        self._session = session or requests.Session()
        self._log_writer = log_writer

    # ----- to be overridden by vendor clients -----

    def build_public_params(self, api_method: str) -> Dict[str, Any]:
        """Produce the static public-params dict expected by this upstream."""

        return {"method": api_method}

    def parse_response(self, *, http_status: int, body: Dict[str, Any]) -> ClientResponse:
        """Map the vendor response body to a ``ClientResponse``."""

        return ClientResponse(
            success=200 <= http_status < 300,
            biz_code=str(body.get("code")) if "code" in body else None,
            biz_sub_code=str(body.get("subCode")) if body.get("subCode") else None,
            message=str(body.get("msg")) if "msg" in body else None,
            data=body.get("result", body),
            raw=body,
            http_status=http_status,
            context_id=(body.get("result") or {}).get("contextId") if isinstance(body.get("result"), dict) else None,
        )

    def is_retryable_business(self, response: ClientResponse) -> bool:  # noqa: ARG002
        """Override to mark some upstream business codes as retryable."""

        return False

    # ----- core call -----

    def call(
        self,
        api_method: str,
        biz_content: Any,
        *,
        sync_run_id: Optional[str] = None,
        db: Optional[Session] = None,
    ) -> ClientResponse:
        """Execute a single upstream call, with retry + structured logging.

        ``db`` is optional: when provided, every attempt is persisted into
        ``integration_api_call_logs``. ``sync_run_id`` lets the row link back
        to the originating sync run.
        """

        public = self.build_public_params(api_method)
        public, headers = self.signer.sign(public_params=public, biz_content=biz_content)
        # Belt-and-suspenders: if the vendor signer didn't already attach a
        # business-payload field (covering both ``bizcontent`` and the older
        # snake-case ``biz_content`` spelling), drop one in so the request is
        # still well-formed.
        if "bizcontent" not in public and "biz_content" not in public:
            public["bizcontent"] = _serialize_biz_content(biz_content)

        attempt = 0
        last_error: Optional[Exception] = None
        while attempt <= self.max_retries:
            attempt += 1
            started_at = _utcnow()
            t0 = time.perf_counter()
            response: Optional[ClientResponse] = None
            error_message: Optional[str] = None
            http_status: Optional[int] = None
            body_raw: Dict[str, Any] = {}
            try:
                resp = self._session.post(
                    self.base_url,
                    data=public,
                    headers=headers,
                    timeout=self.timeout_seconds,
                )
                http_status = resp.status_code
                body_raw = _safe_json(resp)
                response = self.parse_response(http_status=resp.status_code, body=body_raw)
                duration_ms = int((time.perf_counter() - t0) * 1000)
                response.duration_ms = duration_ms
                response.request_payload = public

                # Trust the vendor's ``parse_response`` to flatten framework
                # vs. business status into a single boolean. Some upstreams
                # (e.g. Jackyun) use ``code: 0`` rather than ``code: 200`` for
                # success, so don't second-guess ``biz_code`` here.
                if response.success:
                    self._write_log(
                        db=db,
                        sync_run_id=sync_run_id,
                        api_method=api_method,
                        public=public,
                        body=body_raw,
                        response=response,
                        started_at=started_at,
                        error_message=None,
                    )
                    return response

                # parse upstream error
                err = self._classify_error(api_method, response)
                self._write_log(
                    db=db,
                    sync_run_id=sync_run_id,
                    api_method=api_method,
                    public=public,
                    body=body_raw,
                    response=response,
                    started_at=started_at,
                    error_message=err.message,
                )
                if err.retryable and attempt <= self.max_retries:
                    last_error = err
                    time.sleep(self.retry_backoff_seconds * attempt)
                    continue
                raise err
            except requests.RequestException as exc:
                duration_ms = int((time.perf_counter() - t0) * 1000)
                error_message = str(exc) or exc.__class__.__name__
                err = IntegrationTransportError(
                    error_message,
                    source_system=self.source_system,
                    api_method=api_method,
                )
                self._write_log(
                    db=db,
                    sync_run_id=sync_run_id,
                    api_method=api_method,
                    public=public,
                    body=body_raw,
                    response=None,
                    started_at=started_at,
                    error_message=error_message,
                    http_status=http_status,
                    duration_ms=duration_ms,
                )
                if attempt <= self.max_retries:
                    last_error = err
                    time.sleep(self.retry_backoff_seconds * attempt)
                    continue
                raise err
        # we should never get here, but keep type-checker happy
        raise last_error or IntegrationTransportError(
            "exhausted retries",
            source_system=self.source_system,
            api_method=api_method,
        )

    # ----- helpers -----

    def _classify_error(self, api_method: str, response: ClientResponse) -> IntegrationError:
        msg = response.message or "upstream error"
        ctx = {
            "source_system": self.source_system,
            "api_method": api_method,
            "biz_code": response.biz_code,
            "biz_sub_code": response.biz_sub_code,
            "http_status": response.http_status,
            "context_id": response.context_id,
        }
        # very loose heuristic: upstream auth/sign/forbidden codes -> auth error
        sub = (response.biz_sub_code or "").lower()
        if any(token in sub for token in ("auth", "sign", "forbidden", "denied")):
            return IntegrationAuthError(msg, **ctx)
        if self.is_retryable_business(response):
            err = IntegrationBusinessError(msg, **ctx)
            err.retryable = True
            return err
        return IntegrationBusinessError(msg, **ctx)

    def _write_log(
        self,
        *,
        db: Optional[Session],
        sync_run_id: Optional[str],
        api_method: str,
        public: Dict[str, Any],
        body: Dict[str, Any],
        response: Optional[ClientResponse],
        started_at: datetime,
        error_message: Optional[str],
        http_status: Optional[int] = None,
        duration_ms: Optional[int] = None,
    ) -> None:
        if db is None and self._log_writer is None:
            return
        log_row = {
            "id": str(uuid.uuid4()),
            "sync_run_id": sync_run_id,
            "source_system": self.source_system,
            "api_method": api_method,
            "direction": "outbound",
            "http_status": response.http_status if response else http_status,
            "biz_code": response.biz_code if response else None,
            "biz_sub_code": response.biz_sub_code if response else None,
            "duration_ms": response.duration_ms if response else duration_ms,
            "context_id": response.context_id if response else None,
            "request_json": _truncate_for_log(_redact_secrets(public)),
            "response_json": _truncate_for_log(body),
            "error_message": error_message,
            "requested_at": started_at,
        }
        if self._log_writer is not None:
            self._log_writer(log_row)
            return

        # Lazy import to avoid circulars in test bootstrap.
        from ...planner import models as planner_models  # type: ignore

        row = planner_models.IntegrationApiCallLog(
            id=log_row["id"],
            sync_run_id=log_row["sync_run_id"],
            source_system=log_row["source_system"],
            api_method=log_row["api_method"],
            direction=log_row["direction"],
            http_status=log_row["http_status"],
            biz_code=log_row["biz_code"],
            biz_sub_code=log_row["biz_sub_code"],
            duration_ms=log_row["duration_ms"],
            context_id=log_row["context_id"],
            request_json=log_row["request_json"],
            response_json=log_row["response_json"],
            error_message=log_row["error_message"],
            requested_at=log_row["requested_at"],
        )
        db.add(row)


def _serialize_biz_content(biz_content: Any) -> str:
    if biz_content is None:
        return "{}"
    if isinstance(biz_content, str):
        return biz_content
    return json.dumps(biz_content, ensure_ascii=False, sort_keys=True)


def _safe_json(resp: requests.Response) -> Dict[str, Any]:
    try:
        body = resp.json()
        if isinstance(body, dict):
            return body
        return {"_non_dict_body": body}
    except ValueError:
        return {"_text_body": resp.text[:4000]}


_REDACTED_KEYS = {"sign", "secret", "appsecret", "token", "authorization"}


def _redact_secrets(payload: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k, v in payload.items():
        if str(k).lower() in _REDACTED_KEYS:
            out[k] = "***"
        else:
            out[k] = v
    return out

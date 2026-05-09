"""Unified error hierarchy for all upstream integrations.

Why a small class hierarchy:
- We want callers to differentiate "should retry vs should not" without
  inspecting vendor-specific codes.
- Sync runner / writeback worker convert these into structured rows in
  ``integration_sync_runs.error_message`` / ``integration_writeback_jobs.last_error``.
"""

from __future__ import annotations

from typing import Any, Dict, Optional


class IntegrationError(Exception):
    """Base class for all integration-layer errors."""

    retryable: bool = False

    def __init__(
        self,
        message: str,
        *,
        source_system: Optional[str] = None,
        api_method: Optional[str] = None,
        biz_code: Optional[str] = None,
        biz_sub_code: Optional[str] = None,
        http_status: Optional[int] = None,
        context_id: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.source_system = source_system
        self.api_method = api_method
        self.biz_code = biz_code
        self.biz_sub_code = biz_sub_code
        self.http_status = http_status
        self.context_id = context_id
        self.payload = payload or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": type(self).__name__,
            "message": self.message,
            "source_system": self.source_system,
            "api_method": self.api_method,
            "biz_code": self.biz_code,
            "biz_sub_code": self.biz_sub_code,
            "http_status": self.http_status,
            "context_id": self.context_id,
            "retryable": self.retryable,
        }


class IntegrationAuthError(IntegrationError):
    """Signature / token / authorization failures. Usually NOT retryable."""

    retryable = False


class IntegrationBusinessError(IntegrationError):
    """Upstream returned a structured business error (param invalid, status not allowed, ...).

    Default not retryable; callers can override per error code.
    """

    retryable = False


class IntegrationTransportError(IntegrationError):
    """Network / timeout / 5xx. Retryable by default."""

    retryable = True

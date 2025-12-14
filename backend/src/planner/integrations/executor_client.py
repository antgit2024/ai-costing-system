from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Dict

import httpx

from ...config import settings
from ..services import metrics

logger = logging.getLogger(__name__)


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 3, reset_timeout: int = 30) -> None:
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.failure_count = 0
        self.last_failure: float | None = None

    def record_success(self) -> None:
        self.failure_count = 0
        self.last_failure = None

    def record_failure(self) -> None:
        self.failure_count += 1
        self.last_failure = time.time()

    def allow_request(self) -> bool:
        if self.failure_count < self.failure_threshold:
            return True
        if self.last_failure and (time.time() - self.last_failure) > self.reset_timeout:
            self.failure_count = 0
            self.last_failure = None
            return True
        return False


class ExecutorClient:
    def __init__(self) -> None:
        self.base_url = settings.executor_base_url.rstrip("/")
        self.api_key = settings.executor_api_key
        self.mock_mode = settings.feature_flag_mock_integrations
        self.breaker = CircuitBreaker()
        self.timeout = 10
        self.max_attempts = 3

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def export_scenario(self, payload: Dict[str, Any], trace_id: str) -> Dict[str, Any]:
        metrics.executor_requests.labels(status="attempt").inc()
        if self.mock_mode:
            logger.info("executor_mock_export trace=%s payload=%s", trace_id, payload)
            metrics.executor_requests.labels(status="success").inc()
            return {"status": "accepted", "reference_id": f"MOCK-{payload['scenario_id']}"}

        if not self.breaker.allow_request():
            metrics.executor_requests.labels(status="circuit_open").inc()
            raise RuntimeError("Executor circuit breaker open")

        attempt = 0
        last_exc: Exception | None = None
        while attempt < self.max_attempts:
            attempt += 1
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    response = client.post(
                        f"{self.base_url}/exports",
                        json=payload,
                        headers={**self._headers(), "X-Trace-Id": trace_id},
                    )
                response.raise_for_status()
                data = response.json()
                metrics.executor_requests.labels(status="success").inc()
                self.breaker.record_success()
                return data
            except Exception as exc:  # pragma: no cover - HTTP failure branch
                last_exc = exc
                self.breaker.record_failure()
                metrics.executor_requests.labels(status="failure").inc()
                logger.warning(
                    "executor_export_failed trace=%s attempt=%s error=%s", trace_id, attempt, exc
                )
                time.sleep(min(2 ** attempt, 5))

        raise RuntimeError(f"Executor export failed after retries: {last_exc}")


_executor_client: ExecutorClient | None = None


def get_executor_client() -> ExecutorClient:
    global _executor_client
    if _executor_client is None:
        _executor_client = ExecutorClient()
    return _executor_client


def generate_trace_id() -> str:
    return str(uuid.uuid4())


def reset_client() -> None:
    global _executor_client
    _executor_client = None

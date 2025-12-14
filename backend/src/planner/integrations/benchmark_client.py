from __future__ import annotations

import logging
import time
from typing import Any, Dict

import httpx
from cachetools import TTLCache

from ...config import settings
from ..services import metrics

logger = logging.getLogger(__name__)

_cache = TTLCache(maxsize=128, ttl=settings.benchmark_cache_ttl_seconds)


def _mock_response(category: str, metric: str, source: str = "mock") -> Dict[str, Any]:
    return {
        "category": category,
        "metric": metric,
        "items": [
            {"value": 4.5, "confidence": 0.66},
            {"value": 5.1, "confidence": 0.61},
        ],
        "source": source,
    }


class BenchmarkClient:
    def __init__(self) -> None:
        self.base_url = settings.benchmark_api_base_url.rstrip("/")
        self.api_key = settings.benchmark_api_key
        self.mock_mode = settings.feature_flag_mock_integrations
        self.timeout = 10

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        return headers

    def _cache_and_return(self, cache_key: tuple[str, str], data: Dict[str, Any]) -> Dict[str, Any]:
        _cache[cache_key] = data
        return data

    def fetch(self, category: str, metric: str) -> Dict[str, Any]:
        cache_key = (category, metric)
        cached = _cache.get(cache_key)
        if cached:
            return cached

        metrics.benchmark_requests.labels(status="attempt").inc()
        if self.mock_mode:
            data = _mock_response(category, metric, source="mock")
            metrics.benchmark_requests.labels(status="success").inc()
            return self._cache_and_return(cache_key, data)

        start = time.time()
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(
                    f"{self.base_url}/benchmarks",
                    params={"category": category, "metric": metric},
                    headers=self._headers(),
                )
            response.raise_for_status()
            data = response.json()
            metrics.benchmark_requests.labels(status="success").inc()
            metrics.external_latency.labels("benchmark").observe(time.time() - start)
            return self._cache_and_return(cache_key, data)
        except Exception as exc:  # pragma: no cover - network errors
            metrics.benchmark_requests.labels(status="failure").inc()
            metrics.external_latency.labels("benchmark").observe(time.time() - start)
            logger.error("Benchmark API failure (category=%s metric=%s): %s", category, metric, exc)
            if cached:
                cached["source"] = cached.get("source", "cache")
                return cached
            if settings.benchmark_fail_open or self.mock_mode:
                logger.warning("Benchmark fallback engaged for %s/%s", category, metric)
                data = _mock_response(category, metric, source="fallback")
                return self._cache_and_return(cache_key, data)
            raise RuntimeError("Benchmark service unavailable") from exc


def get_client() -> BenchmarkClient:
    return BenchmarkClient()


def clear_cache() -> None:
    _cache.clear()


def clear_cache() -> None:
    _cache.clear()

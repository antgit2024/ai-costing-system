from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.responses import Response

from ...config import settings

executor_requests = Counter(
    "planner_executor_requests_total",
    "Total executor export attempts",
    labelnames=["status"],
)
benchmark_requests = Counter(
    "planner_benchmark_requests_total",
    "Total benchmark API requests",
    labelnames=["status"],
)
message_bus_events = Counter(
    "planner_message_bus_events_total",
    "Planner events published to message bus",
    labelnames=["event_type"],
)
external_latency = Histogram(
    "planner_external_call_duration_seconds",
    "Latency for external integrations",
    labelnames=["integration"],
)

router = APIRouter()


def _require_metrics_enabled():
    if not settings.metrics_enabled:
        raise HTTPException(status_code=404, detail="Metrics disabled")


@router.get("/metrics")
def metrics_endpoint(_: None = Depends(_require_metrics_enabled)) -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

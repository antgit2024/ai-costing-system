from __future__ import annotations

import logging
from typing import Any, Dict, List

from ..integrations import message_bus

logger = logging.getLogger(__name__)

_EVENT_LOG: List[Dict[str, Any]] = []


def dispatch_event(event_type: str, payload: Dict[str, Any], trace_id: str | None = None) -> None:
    event = {
        "event_type": event_type,
        "payload": payload,
        "trace_id": trace_id,
    }
    _EVENT_LOG.append(event)
    try:
        publisher = message_bus.get_publisher()
        publisher.publish(event)
    except Exception as exc:  # pragma: no cover - logging only
        logger.warning("Failed to publish message bus event %s: %s", event_type, exc)
    logger.info("planner_event %s %s", event_type, payload)


def get_events() -> List[Dict[str, Any]]:
    return list(_EVENT_LOG)


def clear_events() -> None:
    _EVENT_LOG.clear()

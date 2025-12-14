from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict

try:  # optional dependency
    from kafka import KafkaProducer  # type: ignore
except Exception:  # pragma: no cover - kafka optional
    KafkaProducer = None  # type: ignore

from ...config import settings
from ..services import metrics

logger = logging.getLogger(__name__)

_PUBLISHED_EVENTS: list[Dict[str, Any]] = []


class MessageBusPublisher:
    def __init__(self) -> None:
        self.broker = settings.message_bus_broker
        self.topic = settings.message_bus_topic
        self._producer = None
        if self.broker and KafkaProducer:
            try:
                self._producer = KafkaProducer(
                    bootstrap_servers=self.broker,
                    value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                )
            except Exception as exc:  # pragma: no cover - depends on infra
                logger.warning("Failed to initialize Kafka producer: %s", exc)
                self._producer = None

    def publish(self, event: Dict[str, Any]) -> None:
        event_type = event.get("event_type", "unknown")
        if self._producer:
            for attempt in range(1, settings.message_bus_max_retries + 1):
                try:
                    future = self._producer.send(self.topic, event)
                    future.get(timeout=settings.message_bus_publish_timeout)
                    self._producer.flush()
                    metrics.message_bus_events.labels(event_type=event_type).inc()
                    return
                except Exception as exc:  # pragma: no cover - depends on infra
                    logger.warning(
                        "Message bus publish failed (attempt %s/%s): %s",
                        attempt,
                        settings.message_bus_max_retries,
                        exc,
                    )
                    time.sleep(min(0.5 * attempt, 2))
        logger.error("message_bus_fallback storing event locally: %s", event_type)
        _PUBLISHED_EVENTS.append(event)
        metrics.message_bus_events.labels(event_type=event_type).inc()


_publisher: MessageBusPublisher | None = None


def get_publisher() -> MessageBusPublisher:
    global _publisher
    if _publisher is None:
        _publisher = MessageBusPublisher()
    return _publisher


def get_published_events() -> list[Dict[str, Any]]:
    return list(_PUBLISHED_EVENTS)


def clear_events() -> None:
    _PUBLISHED_EVENTS.clear()

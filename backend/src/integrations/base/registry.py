"""A tiny in-process client registry.

Each vendor module registers a factory at import time
(e.g. ``register_client("jackyun", build_jackyun_client)``).
Sync runners / writeback workers can then resolve clients by source_system
without importing concrete classes.
"""

from __future__ import annotations

from typing import Callable, Dict

from .client import BaseClient

_FACTORIES: Dict[str, Callable[[], BaseClient]] = {}


def register_client(source_system: str, factory: Callable[[], BaseClient]) -> None:
    key = (source_system or "").strip().lower()
    if not key:
        raise ValueError("source_system is required")
    _FACTORIES[key] = factory


def get_client(source_system: str) -> BaseClient:
    key = (source_system or "").strip().lower()
    if key not in _FACTORIES:
        raise KeyError(f"no integration client registered for source_system={source_system!r}")
    return _FACTORIES[key]()


def available_clients() -> list[str]:
    return sorted(_FACTORIES.keys())

"""Runtime compatibility helpers for the planner backend."""

from __future__ import annotations

import sys
from typing import ForwardRef

_PATCHED_ATTR = "__planner_forward_ref_patched__"


def ensure_forward_ref_compat() -> None:
    """Patch typing.ForwardRef for Python 3.12 so Pydantic v1 continues to work."""

    if sys.version_info < (3, 12):  # pragma: no cover - only needed on 3.12+
        return

    original = getattr(ForwardRef, "_evaluate", None)
    if original is None:
        return

    if getattr(original, _PATCHED_ATTR, False):  # already patched
        return

    def _compat(self, globalns, localns, type_params=None, *, recursive_guard=None):
        if recursive_guard is None:
            recursive_guard = set()
        return original(self, globalns, localns, type_params, recursive_guard=recursive_guard)

    setattr(_compat, _PATCHED_ATTR, True)
    ForwardRef._evaluate = _compat


# Patch immediately when module is imported.
ensure_forward_ref_compat()

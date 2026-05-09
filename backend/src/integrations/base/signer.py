"""Signing abstraction.

Each upstream may use a different signing scheme (Jackyun MD5 with secret,
HMAC-SHA256, OAuth Bearer, ...). A ``Signer`` is responsible for:

- mutating the public params dict to add ``sign``/``timestamp``/etc; and/or
- producing HTTP headers (e.g. ``Authorization: Bearer ...``).

Concrete signers live in each vendor subpackage.
"""

from __future__ import annotations

from typing import Any, Dict, Protocol, Tuple


class Signer(Protocol):
    """A signer takes the public params and returns the signed params + headers."""

    def sign(
        self,
        *,
        public_params: Dict[str, Any],
        biz_content: Any,
    ) -> Tuple[Dict[str, Any], Dict[str, str]]:
        ...


class NullSigner:
    """Pass-through signer for upstreams that don't require signing in dev."""

    def sign(
        self,
        *,
        public_params: Dict[str, Any],
        biz_content: Any,  # noqa: ARG002 - kept for protocol parity
    ) -> Tuple[Dict[str, Any], Dict[str, str]]:
        return dict(public_params), {}

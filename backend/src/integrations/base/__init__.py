"""
Generic infrastructure shared by all upstream integrations.

The goal is to keep vendor-specific code thin: each upstream only implements
``Signer`` (if any) + ``BaseClient`` subclass + a few API-method functions and
mappers, while sync orchestration / call logging / writeback queueing all live
here so they behave identically across vendors.
"""

from .errors import (
    IntegrationError,
    IntegrationAuthError,
    IntegrationBusinessError,
    IntegrationTransportError,
)
from .client import BaseClient, ClientResponse
from .signer import Signer, NullSigner
from .registry import register_client, get_client, available_clients
from .sync_runner import SyncRunContext, run_sync
from .watermark import (
    get_watermark,
    get_watermark_value,
    set_watermark,
    advance_watermark_if_newer,
)
from .dead_letter import record_dead_letter, list_open_dead_letters, resolve_dead_letter
from .writeback import enqueue_writeback, claim_due_writebacks, mark_writeback_result

__all__ = [
    "IntegrationError",
    "IntegrationAuthError",
    "IntegrationBusinessError",
    "IntegrationTransportError",
    "BaseClient",
    "ClientResponse",
    "Signer",
    "NullSigner",
    "register_client",
    "get_client",
    "available_clients",
    "SyncRunContext",
    "run_sync",
    "get_watermark",
    "get_watermark_value",
    "set_watermark",
    "advance_watermark_if_newer",
    "record_dead_letter",
    "list_open_dead_letters",
    "resolve_dead_letter",
    "enqueue_writeback",
    "claim_due_writebacks",
    "mark_writeback_result",
]

"""
Unified external-system integrations layer.

Subpackages:
- base: shared HTTP client / signing / errors / sync runner / writeback worker.
- jackyun: Jackyun ERP/WMS open API (shipments, after-sales, goods, memo writeback).
- pod: POD design platform (placeholder).

All upstream calls share a single audit trail via ``integration_api_call_logs``,
record archival via ``integration_api_records``, sync coordination via
``integration_sync_runs``, and writeback queueing via ``integration_writeback_jobs``.
"""

from . import base  # noqa: F401
from . import jackyun  # noqa: F401
from . import pod  # noqa: F401

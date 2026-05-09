"""Thin per-method wrappers around ``JackyunClient.call``.

Each function returns the parsed ``data`` portion of the response (i.e.
``response.data``) plus the original raw body when needed for archival.
"""

from . import shipment  # noqa: F401
from . import after_sales  # noqa: F401
from . import goods  # noqa: F401
from . import memo  # noqa: F401

"""Jackyun (吉客云) ERP/WMS open API integration.

Subpackages:
- client: HTTP client + signer
- api: thin wrappers per Jackyun API method
- mappers: payload -> business tables (shipment_lines / after_sales_lines / sku_master)
- sync_jobs: end-to-end sync entrypoints (orchestrate client + mapper + sync_runner)

Convention: business params go inside ``biz_content`` (JSON string), public
params (method/appkey/version/timestamp/sign) live in the form body, signing
strips ``sign`` and ``token`` then MD5-wraps the sorted ``key+value`` string
with the app secret on both ends.
"""

from .client import JackyunClient, JackyunSigner, build_default_client
from . import api  # noqa: F401
from . import mappers  # noqa: F401
from . import sync_jobs  # noqa: F401
from ..base.registry import register_client


register_client("jackyun", build_default_client)


__all__ = [
    "JackyunClient",
    "JackyunSigner",
    "build_default_client",
]

from __future__ import annotations

import ipaddress
from typing import Iterable, List, Optional, Union

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


_Net = Union[ipaddress.IPv4Network, ipaddress.IPv6Network]
_Addr = Union[ipaddress.IPv4Address, ipaddress.IPv6Address]


def _parse_allowlist(raw: Optional[str]) -> List[_Net]:
    """
    Parse comma-separated allowlist into ip networks.
    - "1.2.3.4" will be treated as "1.2.3.4/32" (or /128 for IPv6)
    - "1.2.3.0/24" is supported
    """
    if not raw:
        return []
    items = [x.strip() for x in str(raw).split(",") if x.strip()]
    nets: List[_Net] = []
    for item in items:
        try:
            if "/" in item:
                nets.append(ipaddress.ip_network(item, strict=False))
            else:
                addr = ipaddress.ip_address(item)
                nets.append(ipaddress.ip_network(addr.exploded + ("/32" if addr.version == 4 else "/128"), strict=False))
        except Exception:
            # Ignore malformed entries rather than crashing the whole app.
            continue
    return nets


def _extract_client_ip(request: Request, trust_proxy_headers: bool) -> Optional[str]:
    if trust_proxy_headers:
        xff = request.headers.get("x-forwarded-for")
        if xff:
            # The left-most is the original client (common convention).
            return xff.split(",")[0].strip()
        xri = request.headers.get("x-real-ip")
        if xri:
            return xri.strip()
    if request.client:
        return request.client.host
    return None


def _is_allowed(client_ip: Optional[str], nets: Iterable[_Net]) -> bool:
    if not client_ip:
        return False
    try:
        ip: _Addr = ipaddress.ip_address(client_ip)
    except Exception:
        return False
    for net in nets:
        if ip in net:
            return True
    return False


class IPAllowlistMiddleware(BaseHTTPMiddleware):
    """
    A very lightweight access control for pre-auth phase.
    - If allowlist is empty, middleware is a no-op.
    - If set, deny requests whose client ip is not in allowlist.
    """

    def __init__(
        self,
        app,
        *,
        allowlist_raw: Optional[str],
        trust_proxy_headers: bool = False,
        exclude_paths: Optional[list[str]] = None,
    ):
        super().__init__(app)
        self._nets = _parse_allowlist(allowlist_raw)
        self._trust_proxy_headers = bool(trust_proxy_headers)
        self._exclude_paths = set(exclude_paths or [])

    async def dispatch(self, request: Request, call_next) -> Response:
        if not self._nets:
            return await call_next(request)
        if request.url.path in self._exclude_paths:
            return await call_next(request)

        client_ip = _extract_client_ip(request, self._trust_proxy_headers)
        if _is_allowed(client_ip, self._nets):
            return await call_next(request)

        return JSONResponse(
            status_code=403,
            content={
                "detail": "IP_NOT_ALLOWED",
                "client_ip": client_ip,
            },
        )


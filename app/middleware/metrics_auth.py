"""Optional IP allowlist for /metrics endpoint."""

from __future__ import annotations

import ipaddress
import os

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


def _allowed_ips() -> list:
    raw = os.getenv("METRICS_ALLOWED_IPS", "").strip()
    if not raw:
        return []
    entries: list[ipaddress._BaseNetwork | ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            if "/" in part:
                entries.append(ipaddress.ip_network(part, strict=False))
            else:
                entries.append(ipaddress.ip_address(part))
        except ValueError:
            continue
    return entries


def _ip_allowed(ip: str, allowed: list) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    for entry in allowed:
        if isinstance(entry, (ipaddress.IPv4Network, ipaddress.IPv6Network)):
            if addr in entry:
                return True
        elif addr == entry:
            return True
    return False


class MetricsAuthMiddleware(BaseHTTPMiddleware):
    """Restrict /metrics when METRICS_ALLOWED_IPS is set."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path != "/metrics":
            return await call_next(request)

        allowed = _allowed_ips()
        if not allowed:
            return await call_next(request)

        client = _client_ip(request)
        if client and _ip_allowed(client, allowed):
            return await call_next(request)

        return JSONResponse(status_code=403, content={"detail": "Metrics access denied"})

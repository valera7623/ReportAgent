"""Validate webhook URLs — block internal/private targets."""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

from app.webhook.config import WEBHOOK_MAX_URL_LENGTH

_BLOCKED_HOSTS = frozenset(
    {
        "localhost",
        "localhost.localdomain",
        "metadata.google.internal",
    }
)


def validate_webhook_url(url: str) -> None:
    """
    Raise ValueError if URL is invalid or points to internal network.

    Only http/https schemes allowed.
    """
    if not url or not url.strip():
        raise ValueError("Webhook URL is required")

    cleaned = url.strip()
    if len(cleaned) > WEBHOOK_MAX_URL_LENGTH:
        raise ValueError(f"Webhook URL exceeds maximum length ({WEBHOOK_MAX_URL_LENGTH})")

    parsed = urlparse(cleaned)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Webhook URL must use http or https scheme")

    if not parsed.netloc:
        raise ValueError("Webhook URL must include a host")

    host = parsed.hostname
    if not host:
        raise ValueError("Webhook URL must include a valid hostname")

    lower_host = host.lower()
    if lower_host in _BLOCKED_HOSTS or lower_host.endswith(".local"):
        raise ValueError("Webhook URL must not target localhost or .local hosts")

    # Literal IP check
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        pass  # hostname, not a literal IP
    else:
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise ValueError("Webhook URL must not target private or internal IP addresses")

    # DNS resolution guard (best-effort)
    try:
        for info in socket.getaddrinfo(host, None):
            addr = info[4][0]
            ip = ipaddress.ip_address(addr)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                raise ValueError("Webhook URL resolves to a private or internal IP address")
    except socket.gaierror:
        # Allow URLs that cannot be resolved at registration time (offline DNS)
        pass

"""Admin API key verification and request logging."""

from __future__ import annotations

import os
import secrets
from typing import Any

from app.utils.logger import get_logger

logger = get_logger("admin_auth", "log_admin.log")

GLOBAL_SCOPE = "__global__"


def _allowed_ips() -> set[str]:
    raw = os.getenv("ADMIN_ALLOWED_IPS", "").strip()
    if not raw:
        return set()
    return {ip.strip() for ip in raw.split(",") if ip.strip()}


def get_admin_api_key() -> str:
    return os.getenv("ADMIN_API_KEY", "").strip()


def verify_admin_key(api_key: str | None, *, client_ip: str | None = None) -> bool:
    """
    Verify admin API key with constant-time comparison.

    Optionally restricts by ADMIN_ALLOWED_IPS when configured.
    """
    expected = get_admin_api_key()
    if not expected:
        logger.error("ADMIN_API_KEY not configured")
        return False

    if not api_key:
        log_admin_action("auth_failed", target=None, details={"reason": "missing_key"}, client_ip=client_ip)
        return False

    allowed = _allowed_ips()
    if allowed and client_ip and client_ip not in allowed:
        logger.warning("Admin access denied from IP %s", client_ip)
        log_admin_action(
            "auth_failed",
            target=None,
            details={"reason": "ip_not_allowed", "ip": client_ip},
            client_ip=client_ip,
        )
        return False

    if not secrets.compare_digest(api_key, expected):
        log_admin_action("auth_failed", target=None, details={"reason": "invalid_key"}, client_ip=client_ip)
        logger.warning("Rejected invalid admin API key from %s", client_ip or "unknown")
        return False

    return True


def log_admin_action(
    action: str,
    *,
    target: str | None = None,
    details: dict[str, Any] | None = None,
    client_ip: str | None = None,
) -> None:
    """Log admin action to log_admin.log and audit_log table."""
    import json

    detail_str = json.dumps(details, ensure_ascii=False) if details else None
    logger.info(
        "action=%s target=%s ip=%s details=%s",
        action,
        target or "-",
        client_ip or "-",
        detail_str or "-",
    )
    try:
        from app.db.admin_queries import insert_audit_log

        insert_audit_log(action=action, target=target, details=detail_str, admin_ip=client_ip)
    except Exception as exc:
        logger.warning("Failed to write audit log: %s", exc)

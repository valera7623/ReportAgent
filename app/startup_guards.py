"""Production startup guards — refuse unsafe configuration."""

from __future__ import annotations

import os
from urllib.parse import urlparse

from app.utils.logger import get_logger

logger = get_logger("startup_guards", "log_api.log")

_PLACEHOLDER_SECRETS = frozenset(
    {
        "",
        "change-me",
        "change-me-generate-on-deploy",
        "changeme",
        "secret",
        "jwt-secret",
        "your-secret-key",
    }
)

_LOCAL_HOSTS = frozenset(
    {
        "",
        "localhost",
        "127.0.0.1",
        "0.0.0.0",
        "::1",
    }
)


def _truthy(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in ("1", "true", "yes")


def _domain_host() -> str:
    raw = (
        os.getenv("DOMAIN", "").strip()
        or os.getenv("SITE_URL", "").strip()
        or os.getenv("FRONTEND_URL", "").strip()
    )
    if not raw:
        return ""
    if "://" not in raw:
        return raw.split("/")[0].split(":")[0].lower()
    parsed = urlparse(raw)
    return (parsed.hostname or "").lower()


def _is_local_domain(host: str) -> bool:
    if not host or host in _LOCAL_HOSTS:
        return True
    if host.endswith(".localhost"):
        return True
    if host.endswith(".local"):
        return True
    return False


def _is_placeholder(value: str) -> bool:
    v = (value or "").strip().lower()
    if v in _PLACEHOLDER_SECRETS:
        return True
    if v.startswith("change-me"):
        return True
    return len(v) < 16


def validate_production_config() -> None:
    """Raise RuntimeError if production-like DOMAIN has unsafe settings."""
    host = _domain_host()
    local = _is_local_domain(host)
    errors: list[str] = []

    if _truthy("DISABLE_AUTH") and not local:
        errors.append(
            "DISABLE_AUTH=true is not allowed when DOMAIN/SITE_URL is a public host "
            f"({host or 'set'}). Use localhost for local development only."
        )

    admin_key = os.getenv("ADMIN_API_KEY", "").strip()
    if not local and _is_placeholder(admin_key):
        errors.append(
            "ADMIN_API_KEY is missing or still a placeholder. "
            "Generate a strong key before deploying to production."
        )

    jwt_secret = os.getenv("JWT_SECRET_KEY", "").strip() or os.getenv("JWT_SECRET", "").strip()
    if not local and _is_placeholder(jwt_secret):
        errors.append(
            "JWT_SECRET_KEY is missing or too weak/placeholder. "
            "Set a strong random secret (16+ chars) for production."
        )

    if errors:
        for msg in errors:
            logger.error("Startup guard failed: %s", msg)
        raise RuntimeError("Unsafe production configuration:\n- " + "\n- ".join(errors))

    if _truthy("DISABLE_AUTH") and local:
        logger.warning("DISABLE_AUTH=true — authentication bypassed (local/dev only)")

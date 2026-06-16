"""API key generation, verification, and lifecycle management."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any

from app.db.database import get_connection, mask_api_key
from app.models.api_key import ApiKeyResponse
from app.utils.logger import get_logger
from app.utils.metrics import (
    record_api_key_auth_failure,
    record_api_key_generated,
    record_api_key_revoked,
)

logger = get_logger("key_management", "log_api.log")

KEY_PREFIX = "ra_"


def _now_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def _row_to_response(row: Any) -> ApiKeyResponse:
    return ApiKeyResponse(
        id=row["id"],
        key_prefix=row["key_prefix"],
        name=row["name"] or "Default",
        created_at=row["created_at"],
        last_used_at=row["last_used_at"],
        expires_at=row["expires_at"],
        is_active=bool(row["is_active"]),
    )


def _is_expired(expires_at: str | None) -> bool:
    if not expires_at:
        return False
    try:
        exp = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        return exp < datetime.now(timezone.utc)
    except (ValueError, TypeError):
        return False


def generate_api_key(
    user_id: str,
    name: str = "Default",
    expires_at: datetime | None = None,
    *,
    last_used_ip: str | None = None,
) -> tuple[str, str]:
    """
    Generate a new API key for the user.

    Returns (full_key, key_id). The full key is shown only once to the caller.
    """
    key = f"{KEY_PREFIX}{secrets.token_urlsafe(32)}"
    key_hash = _hash_key(key)
    key_prefix = key[:8]
    key_id = str(uuid.uuid4())
    expires_str = (
        expires_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        if expires_at
        else None
    )

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO api_keys (
                id, user_id, key_hash, key_prefix, name, expires_at, is_active
            ) VALUES (?, ?, ?, ?, ?, ?, 1)
            """,
            (key_id, user_id, key_hash, key_prefix, name, expires_str),
        )

    record_api_key_generated()
    logger.info(
        "Generated API key %s (id=%s) for user %s",
        mask_api_key(key),
        key_id,
        user_id,
    )
    return key, key_id


def verify_api_key(
    key: str,
    *,
    client_ip: str | None = None,
) -> dict[str, Any] | None:
    """
    Verify an API key against api_keys table and legacy users.api_key.

    Returns dict with user_id, key_id (or None for pure legacy), source on success.
    Updates last_used_at on success.
    """
    if not key:
        record_api_key_auth_failure("invalid")
        return None

    key_hash = _hash_key(key)
    now = _now_str()

    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT ak.id, ak.user_id, ak.is_active, ak.expires_at, u.is_active AS user_active
            FROM api_keys ak
            JOIN users u ON u.id = ak.user_id
            WHERE ak.key_hash = ?
            """,
            (key_hash,),
        ).fetchone()

        if row is not None:
            if not row["is_active"]:
                record_api_key_auth_failure("revoked")
                logger.warning("Rejected revoked API key %s", mask_api_key(key))
                return None
            if not row["user_active"]:
                record_api_key_auth_failure("revoked")
                return None
            if _is_expired(row["expires_at"]):
                record_api_key_auth_failure("expired")
                logger.warning("Rejected expired API key %s", mask_api_key(key))
                return None

            conn.execute(
                """
                UPDATE api_keys
                SET last_used_at = ?, last_used_ip = COALESCE(?, last_used_ip)
                WHERE id = ?
                """,
                (now, client_ip, row["id"]),
            )
            conn.execute(
                "UPDATE users SET last_used_at = ? WHERE id = ?",
                (now, row["user_id"]),
            )
            return {
                "user_id": row["user_id"],
                "key_id": row["id"],
                "source": "api_keys",
            }

        legacy_row = conn.execute(
            """
            SELECT id, is_active FROM users WHERE api_key = ?
            """,
            (key,),
        ).fetchone()

        if legacy_row is None:
            record_api_key_auth_failure("invalid")
            logger.warning("Rejected unknown API key %s", mask_api_key(key))
            return None

        if not legacy_row["is_active"]:
            record_api_key_auth_failure("revoked")
            return None

        conn.execute(
            "UPDATE users SET last_used_at = ? WHERE id = ?",
            (now, legacy_row["id"]),
        )

        migrated = conn.execute(
            "SELECT id FROM api_keys WHERE user_id = ? AND key_hash = ?",
            (legacy_row["id"], key_hash),
        ).fetchone()
        key_id = migrated["id"] if migrated else None

        if key_id:
            conn.execute(
                """
                UPDATE api_keys
                SET last_used_at = ?, last_used_ip = COALESCE(?, last_used_ip)
                WHERE id = ?
                """,
                (now, client_ip, key_id),
            )

        logger.debug(
            "Authenticated via legacy users.api_key for user %s",
            legacy_row["id"],
        )
        return {
            "user_id": legacy_row["id"],
            "key_id": key_id,
            "source": "legacy",
        }


def count_active_keys(user_id: str) -> int:
    """Count non-expired active keys for a user."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT expires_at FROM api_keys
            WHERE user_id = ? AND is_active = 1
            """,
            (user_id,),
        ).fetchall()

    count = 0
    for row in rows:
        if not _is_expired(row["expires_at"]):
            count += 1
    return count


def revoke_api_key(key_id: str, user_id: str) -> str | None:
    """
    Deactivate an API key. Returns key_prefix on success, None if not found.

    Raises ValueError if revoking would leave the user with no active keys.
    """
    if count_active_keys(user_id) <= 1:
        raise ValueError("Cannot revoke the last active API key")

    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT key_prefix, is_active FROM api_keys
            WHERE id = ? AND user_id = ?
            """,
            (key_id, user_id),
        ).fetchone()
        if row is None:
            return None
        if not row["is_active"]:
            return row["key_prefix"]

        conn.execute(
            "UPDATE api_keys SET is_active = 0 WHERE id = ? AND user_id = ?",
            (key_id, user_id),
        )

    record_api_key_revoked()
    logger.info("Revoked API key id=%s for user %s", key_id, user_id)
    return row["key_prefix"]


def list_user_keys(user_id: str) -> list[ApiKeyResponse]:
    """Return all API keys for a user (without full key values)."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, key_prefix, name, created_at, last_used_at, expires_at, is_active
            FROM api_keys
            WHERE user_id = ?
            ORDER BY datetime(created_at) DESC
            """,
            (user_id,),
        ).fetchall()
    return [_row_to_response(row) for row in rows]


def get_key_by_id(key_id: str, user_id: str) -> ApiKeyResponse | None:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT id, key_prefix, name, created_at, last_used_at, expires_at, is_active
            FROM api_keys WHERE id = ? AND user_id = ?
            """,
            (key_id, user_id),
        ).fetchone()
    if row is None:
        return None
    return _row_to_response(row)


def rename_api_key(key_id: str, user_id: str, name: str) -> ApiKeyResponse | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM api_keys WHERE id = ? AND user_id = ?",
            (key_id, user_id),
        ).fetchone()
        if row is None:
            return None
        conn.execute(
            "UPDATE api_keys SET name = ? WHERE id = ? AND user_id = ?",
            (name, key_id, user_id),
        )
    return get_key_by_id(key_id, user_id)


def rotate_api_key(
    old_key_id: str,
    user_id: str,
    new_name: str | None = None,
) -> tuple[str, str, str]:
    """
    Revoke old key and create a new one.

    Returns (new_full_key, new_key_id, old_key_prefix).
    """
    old = get_key_by_id(old_key_id, user_id)
    if old is None:
        raise LookupError("API key not found")

    name = new_name or f"{old.name} (rotated)"
    new_key, new_key_id = generate_api_key(user_id, name=name)

    with get_connection() as conn:
        conn.execute(
            "UPDATE api_keys SET is_active = 0 WHERE id = ? AND user_id = ?",
            (old_key_id, user_id),
        )

    record_api_key_revoked()
    logger.info(
        "Rotated API key %s -> %s for user %s",
        old.key_prefix,
        mask_api_key(new_key),
        user_id,
    )
    return new_key, new_key_id, old.key_prefix


def migrate_legacy_api_keys() -> int:
    """
    Copy existing users.api_key values into api_keys (hashed).

    Returns number of keys migrated.
    """
    migrated = 0
    with get_connection() as conn:
        try:
            conn.execute("SELECT 1 FROM api_keys LIMIT 1")
        except Exception:
            return 0

        rows = conn.execute(
            """
            SELECT id, api_key, created_at FROM users
            WHERE api_key IS NOT NULL AND api_key != ''
            """
        ).fetchall()

        for row in rows:
            user_id = row["id"]
            api_key = row["api_key"]
            key_hash = _hash_key(api_key)
            exists = conn.execute(
                "SELECT 1 FROM api_keys WHERE user_id = ? AND key_hash = ?",
                (user_id, key_hash),
            ).fetchone()
            if exists:
                continue

            key_prefix = api_key[:8] if len(api_key) >= 8 else api_key
            key_id = str(uuid.uuid4())
            conn.execute(
                """
                INSERT INTO api_keys (
                    id, user_id, key_hash, key_prefix, name, created_at, is_active
                ) VALUES (?, ?, ?, ?, 'Legacy', ?, 1)
                """,
                (key_id, user_id, key_hash, key_prefix, row["created_at"]),
            )
            migrated += 1

    if migrated:
        logger.info("Migrated %d legacy API key(s) to api_keys table", migrated)
    return migrated

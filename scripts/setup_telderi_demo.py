#!/usr/bin/env python3
"""Create or reset a verified Telderi demo user on the production database.

Run inside the FastAPI container (has app + DB volume mounted):

    docker exec reportagent_fastapi python scripts/setup_telderi_demo.py

Or with custom email/password:

    docker exec -e TELDERI_DEMO_EMAIL=... -e TELDERI_DEMO_PASSWORD=... \\
        reportagent_fastapi python scripts/setup_telderi_demo.py
"""

from __future__ import annotations

import os
import secrets
import string
import sys
import uuid

from app.auth.key_management import generate_api_key
from app.auth.password import hash_password
from app.db.database import get_connection

DEFAULT_EMAIL = "telderi-demo@fileguardian.info"
DEFAULT_CHART_TYPE = "bar"


def _generate_password(length: int = 16) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def setup_demo_user(email: str, password: str) -> dict[str, str]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM users WHERE email = ?",
            (email,),
        ).fetchone()

        if row:
            user_id = row["id"]
            conn.execute(
                """
                UPDATE users
                SET password_hash = ?, is_verified = 1, is_active = 1,
                    verification_token = NULL, verification_token_expires_at = NULL,
                    login_attempts = 0, locked_until = NULL
                WHERE id = ?
                """,
                (hash_password(password), user_id),
            )
            action = "updated"
        else:
            user_id = str(uuid.uuid4())
            placeholder_key = f"pending_{user_id}"
            conn.execute(
                """
                INSERT INTO users (
                    id, api_key, email, password_hash, is_verified, is_active
                ) VALUES (?, ?, ?, ?, 1, 1)
                """,
                (user_id, placeholder_key, email, hash_password(password)),
            )
            conn.execute(
                """
                INSERT INTO preferences (user_id, preferred_chart_type, theme, timezone, extra)
                VALUES (?, ?, 'light', 'UTC', '{}')
                """,
                (user_id, DEFAULT_CHART_TYPE),
            )
            action = "created"

    api_key, _key_id = generate_api_key(user_id, name="Telderi demo")
    return {
        "action": action,
        "user_id": user_id,
        "email": email,
        "password": password,
        "api_key": api_key,
    }


def main() -> int:
    email = os.environ.get("TELDERI_DEMO_EMAIL", DEFAULT_EMAIL).strip()
    password = os.environ.get("TELDERI_DEMO_PASSWORD", "").strip()
    if not password:
        password = _generate_password()

    result = setup_demo_user(email, password)

    print("=== Telderi demo account ===")
    print(f"Status: {result['action']}")
    print(f"User ID: {result['user_id']}")
    print(f"Email: {result['email']}")
    print(f"Password: {result['password']}")
    print(f"API key (save now, shown once): {result['api_key']}")
    print()
    print("Login URL: https://reportagent.fileguardian.info/app#/login")
    print("SPA after login: https://reportagent.fileguardian.info/app#/")
    return 0


if __name__ == "__main__":
    sys.exit(main())

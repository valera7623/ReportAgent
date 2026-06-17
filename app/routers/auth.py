"""Email/password authentication endpoints."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, status

from app.auth.email_service import send_reset_password_email, send_verification_email
from app.auth.jwt import create_jwt, create_verification_token, verify_verification_token
from app.auth.models import (
    RequestResetPassword,
    ResetPassword,
    TokenResponse,
    UserLogin,
    UserRegister,
    VerifyEmail,
)
from app.auth.password import hash_password, verify_password
from app.db.database import DEFAULT_CHART_TYPE, get_connection

router = APIRouter(prefix="/auth", tags=["auth"])

VERIFICATION_TOKEN_EXPIRE_HOURS = int(os.getenv("VERIFICATION_TOKEN_EXPIRE_HOURS", "24"))
RESET_PASSWORD_TOKEN_EXPIRE_HOURS = int(os.getenv("RESET_PASSWORD_TOKEN_EXPIRE_HOURS", "1"))


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


@router.post("/register")
async def register(user_data: UserRegister) -> dict[str, str]:
    if user_data.password != user_data.password_confirm:
        raise HTTPException(status_code=400, detail="Passwords do not match")

    with get_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM users WHERE email = ?",
            (str(user_data.email),),
        ).fetchone()
        if existing:
            raise HTTPException(status_code=400, detail="Email already registered")

        user_id = str(uuid.uuid4())
        password_hash_value = hash_password(user_data.password)
        verification_token = create_verification_token(str(user_data.email))
        placeholder_key = f"pending_{user_id}"
        now = _utcnow()

        conn.execute(
            """
            INSERT INTO users (
                id, api_key, email, password_hash, is_verified, verification_token,
                verification_token_expires_at, created_at
            ) VALUES (?, ?, ?, ?, 0, ?, ?, ?)
            """,
            (
                user_id,
                placeholder_key,
                str(user_data.email),
                password_hash_value,
                verification_token,
                _iso(now + timedelta(hours=VERIFICATION_TOKEN_EXPIRE_HOURS)),
                _iso(now),
            ),
        )
        conn.execute(
            """
            INSERT INTO preferences (user_id, preferred_chart_type, theme, timezone, extra)
            VALUES (?, ?, 'light', 'UTC', '{}')
            """,
            (user_id, DEFAULT_CHART_TYPE),
        )

    send_verification_email(str(user_data.email), verification_token)

    return {
        "status": "success",
        "message": "User created. Please verify your email.",
        "user_id": user_id,
    }


@router.post("/verify")
async def verify_email(data: VerifyEmail) -> dict[str, str]:
    email = verify_verification_token(
        data.token,
        expires_hours=VERIFICATION_TOKEN_EXPIRE_HOURS,
    )
    if email is None or email != str(data.email):
        raise HTTPException(status_code=400, detail="Invalid or expired verification token")

    with get_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE users
            SET is_verified = 1,
                verification_token = NULL,
                verification_token_expires_at = NULL
            WHERE email = ?
            """,
            (email,),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="User not found")

    return {"status": "success", "message": "Email verified successfully"}


@router.post("/login", response_model=TokenResponse)
async def login(data: UserLogin) -> TokenResponse:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT id, email, password_hash, is_verified, is_active, login_attempts, locked_until
            FROM users WHERE email = ?
            """,
            (str(data.email),),
        ).fetchone()

        if row is None:
            raise HTTPException(status_code=401, detail="Invalid email or password")

        user_id = row["id"]
        email = row["email"]
        password_hash_value = row["password_hash"]
        is_verified = row["is_verified"]
        is_active = row["is_active"]
        login_attempts = row["login_attempts"] or 0
        locked_until = row["locked_until"]

        if locked_until:
            locked_until_dt = datetime.fromisoformat(locked_until)
            if locked_until_dt.tzinfo is None:
                locked_until_dt = locked_until_dt.replace(tzinfo=timezone.utc)
            if locked_until_dt > _utcnow():
                raise HTTPException(status_code=403, detail="Account is temporarily locked")

        if not is_active:
            raise HTTPException(status_code=403, detail="Account is blocked")

        if not password_hash_value or not verify_password(data.password, password_hash_value):
            new_attempts = login_attempts + 1
            new_locked_until: str | None = None
            if new_attempts >= 5:
                new_locked_until = _iso(_utcnow() + timedelta(minutes=15))

            conn.execute(
                "UPDATE users SET login_attempts = ?, locked_until = ? WHERE id = ?",
                (new_attempts, new_locked_until, user_id),
            )
            raise HTTPException(status_code=401, detail="Invalid email or password")

        conn.execute(
            """
            UPDATE users
            SET login_attempts = 0, locked_until = NULL, last_login_at = ?
            WHERE id = ?
            """,
            (_iso(_utcnow()), user_id),
        )

    jwt_token = create_jwt(user_id)

    return TokenResponse(
        access_token=jwt_token,
        token_type="bearer",
        user_id=user_id,
        email=email or str(data.email),
        is_verified=bool(is_verified),
    )


@router.post("/request-reset-password")
async def request_reset_password(data: RequestResetPassword) -> dict[str, str]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM users WHERE email = ?",
            (str(data.email),),
        ).fetchone()

        if row is None:
            return {"status": "success", "message": "If the email exists, a reset link was sent"}

        token = create_verification_token(str(data.email))
        conn.execute(
            """
            UPDATE users
            SET reset_password_token = ?, reset_password_token_expires_at = ?
            WHERE id = ?
            """,
            (
                token,
                _iso(_utcnow() + timedelta(hours=RESET_PASSWORD_TOKEN_EXPIRE_HOURS)),
                row["id"],
            ),
        )

    send_reset_password_email(str(data.email), token)

    return {"status": "success", "message": "If the email exists, a reset link was sent"}


@router.post("/reset-password")
async def reset_password(data: ResetPassword) -> dict[str, str]:
    email = verify_verification_token(
        data.token,
        expires_hours=RESET_PASSWORD_TOKEN_EXPIRE_HOURS,
    )
    if email is None:
        raise HTTPException(status_code=400, detail="Invalid or expired token")

    with get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM users WHERE email = ?",
            (email,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="User not found")

        new_hash = hash_password(data.new_password)
        conn.execute(
            """
            UPDATE users
            SET password_hash = ?,
                reset_password_token = NULL,
                reset_password_token_expires_at = NULL,
                login_attempts = 0,
                locked_until = NULL
            WHERE id = ?
            """,
            (new_hash, row["id"]),
        )

    return {"status": "success", "message": "Password reset successfully"}

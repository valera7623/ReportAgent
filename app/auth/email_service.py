"""SMTP email delivery for verification and password reset."""

from __future__ import annotations

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
EMAIL_FROM = os.getenv("EMAIL_FROM") or os.getenv("SMTP_FROM", "noreply@reportagent.com")
FRONTEND_URL = (os.getenv("FRONTEND_URL") or "").rstrip("/")
SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").lower() in ("1", "true", "yes")


def _frontend_link(hash_path: str) -> str:
    base = FRONTEND_URL or "http://localhost:8000/app"
    return f"{base}#{hash_path}"


def send_verification_email(email: str, token: str) -> bool:
    from urllib.parse import quote

    verification_url = _frontend_link(
        f"/verify?email={quote(email)}&token={quote(token)}",
    )

    subject = "Подтверждение email для ReportAgent"
    html = f"""
    <html>
    <body>
        <h2>Добро пожаловать в ReportAgent!</h2>
        <p>Для подтверждения email перейдите по ссылке:</p>
        <p><a href="{verification_url}">Подтвердить email</a></p>
        <p>Ссылка действительна 24 часа.</p>
        <p>Если вы не регистрировались, просто проигнорируйте это письмо.</p>
    </body>
    </html>
    """

    return send_email(email, subject, html)


def send_reset_password_email(email: str, token: str) -> bool:
    from urllib.parse import quote

    reset_url = _frontend_link(f"/reset-password/confirm?token={quote(token)}")

    subject = "Сброс пароля для ReportAgent"
    html = f"""
    <html>
    <body>
        <h2>Сброс пароля</h2>
        <p>Для сброса пароля перейдите по ссылке:</p>
        <p><a href="{reset_url}">Сбросить пароль</a></p>
        <p>Ссылка действительна 1 час.</p>
        <p>Если вы не запрашивали сброс, просто проигнорируйте это письмо.</p>
    </body>
    </html>
    """

    return send_email(email, subject, html)


def send_email(to: str, subject: str, html: str) -> bool:
    if not SMTP_HOST or not SMTP_USER or not SMTP_PASSWORD:
        print(f"SMTP not configured; skipping email to {to}: {subject}")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = EMAIL_FROM
        msg["To"] = to

        part = MIMEText(html, "html")
        msg.attach(part)

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
            if SMTP_USE_TLS:
                server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(EMAIL_FROM, [to], msg.as_string())
        return True
    except Exception as exc:
        print(f"Failed to send email: {exc}")
        return False

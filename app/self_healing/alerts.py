"""Send self-healing alerts via Telegram."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from app.utils.logger import get_logger

logger = get_logger("self_healing_alerts", "log_self_healing.json")


def send_self_healing_alert(
    *,
    agent_name: str,
    error_text: str,
    fix_applied: bool,
    fix_id: str | None = None,
    new_record_id: str | None = None,
) -> None:
    """Notify Telegram about self-healing events (uses same bot as Alertmanager)."""
    if os.getenv("ALERTS_ENABLED", "true").lower() not in ("1", "true", "yes"):
        return

    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        logger.debug("Telegram credentials not configured — skipping self-healing alert")
        return

    domain = os.getenv("DOMAIN", "localhost")
    grafana_domain = os.getenv("GRAFANA_DOMAIN", f"grafana.{domain}")

    if fix_applied:
        status = "✅ Auto-fix applied"
        detail = f"fix_id: <code>{fix_id}</code>"
    else:
        status = "⚠️ New error — manual review needed"
        detail = f"record_id: <code>{new_record_id or 'n/a'}</code>"

    text = (
        f"<b>ReportAgent Self-healing</b>\n"
        f"Agent: <b>{agent_name}</b>\n"
        f"{status}\n"
        f"Error: <code>{error_text[:200]}</code>\n"
        f"{detail}\n"
        f'<a href="https://{grafana_domain}/d/ReportAgent-Main/reportagent-main">Grafana</a>'
    )

    payload = json.dumps(
        {"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    ).encode()
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read().decode())
        if not body.get("ok"):
            logger.warning("Telegram alert failed: %s", body)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        logger.warning("Could not send self-healing Telegram alert: %s", exc)

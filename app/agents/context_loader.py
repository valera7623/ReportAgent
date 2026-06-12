"""Agent: load user preferences before the main pipeline."""

from __future__ import annotations

from typing import Any

from app.db.database import get_preferences_by_api_key, mask_api_key
from app.utils.logger import get_logger

logger = get_logger("agent_context_loader", "log_context_loader.log")


def get_user_preferences(api_key: str | None) -> dict[str, Any]:
    """
    Load preferences for the given API key.

    Returns default preferences when api_key is missing or auth is disabled.
    """
    if not api_key:
        from app.db.database import default_preferences

        return default_preferences()

    prefs = get_preferences_by_api_key(api_key)
    if prefs is None:
        from app.db.database import default_preferences

        logger.warning("No preferences for key %s; using defaults", mask_api_key(api_key))
        return default_preferences()

    logger.info(
        "Loaded preferences for key %s (chart=%s, theme=%s)",
        mask_api_key(api_key),
        prefs.get("preferred_chart_type"),
        prefs.get("theme"),
    )
    return prefs


def load_context(api_key: str | None) -> dict[str, Any]:
    """Return context dict with user preferences for downstream agents."""
    preferences = get_user_preferences(api_key)
    return {"preferences": preferences}

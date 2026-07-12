"""Shared OpenAI client (supports ProxyAPI and other compatible gateways)."""

from __future__ import annotations

import os

from openai import OpenAI


def get_openai_base_url() -> str | None:
    """Return custom API base URL or None for official OpenAI."""
    url = os.getenv("OPENAI_BASE_URL", "").strip()
    return url or None


def create_openai_client(*, timeout: float | None = None) -> OpenAI:
    """
    Build OpenAI SDK client from environment.

    Official OpenAI: OPENAI_API_KEY only
    ProxyAPI.ru:      OPENAI_BASE_URL=https://api.proxyapi.ru/openai/v1
    """
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise ValueError("OPENAI_API_KEY not configured")

    if timeout is None:
        timeout = float(os.getenv("OPENAI_TIMEOUT_SEC", "20"))

    base_url = get_openai_base_url()
    kwargs: dict = {"api_key": api_key, "timeout": timeout, "max_retries": 0}
    if base_url:
        kwargs["base_url"] = base_url
    return OpenAI(**kwargs)

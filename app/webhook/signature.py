"""HMAC-SHA256 webhook signature generation and verification."""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any


def sign_payload(secret: str, payload: dict[str, Any]) -> str:
    """Return hex HMAC-SHA256 signature for JSON body."""
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False, sort_keys=True)
    return hmac.new(
        secret.encode("utf-8"),
        body.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify_signature(secret: str, payload: dict[str, Any], signature: str) -> bool:
    """Constant-time verification of webhook signature."""
    expected = sign_payload(secret, payload)
    return hmac.compare_digest(expected, signature)

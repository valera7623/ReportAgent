"""Extract structured error signatures for RAG search."""

from __future__ import annotations

import re
import traceback
from typing import Any

KEYWORD_STOP = frozenset(
    {
        "the",
        "a",
        "an",
        "is",
        "was",
        "in",
        "at",
        "to",
        "for",
        "of",
        "and",
        "or",
        "not",
        "error",
        "exception",
        "failed",
    }
)


def _extract_keywords(message: str, limit: int = 8) -> list[str]:
    tokens = re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*|\d+", message.lower())
    keywords: list[str] = []
    for token in tokens:
        if token in KEYWORD_STOP or len(token) < 2:
            continue
        if token not in keywords:
            keywords.append(token)
        if len(keywords) >= limit:
            break
    return keywords


def _function_from_traceback(traceback_str: str) -> str | None:
    for line in reversed(traceback_str.splitlines()):
        match = re.search(r'File "[^"]+", line \d+, in (\w+)', line)
        if match:
            return match.group(1)
    return None


def extract_error_signature(
    exception: Exception,
    traceback_str: str,
    *,
    input_size: int | None = None,
) -> dict[str, Any]:
    """
    Build a structured error signature for ChromaDB indexing and search.

    Returns error type, keywords, failing function, and optional input size.
    """
    error_type = type(exception).__name__
    message = str(exception)
    module = type(exception).__module__

    full_type = f"{module}.{error_type}" if module and module != "builtins" else error_type
    if "pandas.errors" in full_type or "ParserError" in error_type:
        full_type = "pandas.errors.ParserError"
    if "RateLimitError" in error_type:
        full_type = "openai.RateLimitError"
    if "SMTPAuthenticationError" in error_type:
        full_type = "smtplib.SMTPAuthenticationError"

    signature = {
        "error_type": full_type,
        "error_class": error_type,
        "message": message[:500],
        "keywords": _extract_keywords(message),
        "function_name": _function_from_traceback(traceback_str),
        "input_size": input_size,
    }
    return signature


def build_search_text(signature: dict[str, Any], stack_trace: str = "") -> str:
    """Combine signature fields into a single string for embedding."""
    parts = [
        signature.get("error_type", ""),
        signature.get("error_class", ""),
        signature.get("message", ""),
        " ".join(signature.get("keywords") or []),
        signature.get("function_name") or "",
        stack_trace[:300],
    ]
    return " ".join(p for p in parts if p).strip()


def format_traceback(exception: Exception) -> str:
    """Return traceback string capped at 500 characters."""
    tb = "".join(traceback.format_exception(type(exception), exception, exception.__traceback__))
    return tb[:500]

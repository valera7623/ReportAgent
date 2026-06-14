"""Apply known fixes and validate results."""

from __future__ import annotations

import ast
import json
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from contextlib import contextmanager
from datetime import datetime, timezone
from difflib import get_close_matches
from typing import Any, Callable

import pandas as pd

from app.self_healing.config import (
    FIX_ATTEMPT_TIMEOUT_SECONDS,
    SAFE_FIX_AGENTS,
    is_healable_error,
)
from app.utils.logger import get_logger

logger = get_logger("self_healing_executor", "log_self_healing.json")

# Thread-local fix context passed to agent retry logic via context dict.
_active_fix_context: dict[str, Any] = {}


def _log_fix_attempt(entry: dict[str, Any]) -> None:
    entry["timestamp"] = datetime.now(timezone.utc).isoformat()
    logger.info("fix_attempt: %s", json.dumps(entry, ensure_ascii=False))


def _parse_solution_code(solution_code: str) -> dict[str, Any] | None:
    """Safely parse solution_code JSON — no eval."""
    if not solution_code or not solution_code.strip():
        return None
    text = solution_code.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    try:
        parsed = ast.literal_eval(text)
        if isinstance(parsed, dict):
            return parsed
    except (ValueError, SyntaxError):
        pass
    return None


@contextmanager
def _pandas_read_csv_patch(read_kwargs: dict[str, Any]):
    original = pd.read_csv

    def patched(*args, **kwargs):
        merged = {**read_kwargs, **kwargs}
        return original(*args, **merged)

    pd.read_csv = patched  # type: ignore[assignment]
    try:
        yield
    finally:
        pd.read_csv = original  # type: ignore[assignment]


@contextmanager
def _matplotlib_agg_backend():
    import matplotlib

    prev = matplotlib.get_backend()
    matplotlib.use("Agg", force=True)
    try:
        yield
    finally:
        try:
            matplotlib.use(prev, force=True)
        except Exception:
            pass


def _apply_fuzzy_columns(context: dict[str, Any]) -> dict[str, Any]:
    """Return context overlay with fuzzy-matched column names."""
    overlay = dict(context)
    missing = overlay.pop("_missing_column", None)
    available = overlay.get("available_columns") or []
    if missing and available:
        matches = get_close_matches(str(missing), [str(c) for c in available], n=1, cutoff=0.6)
        if matches:
            overlay["_column_remap"] = {missing: matches[0]}
    return overlay


class FixExecutor:
    """Execute fix strategies and retry agent calls."""

    def __init__(self, agent_name: str) -> None:
        self.agent_name = agent_name

    def attempt_fix(
        self,
        error: Exception,
        context: dict[str, Any],
        similar_fixes: list[dict[str, Any]],
        retry_fn: Callable[[], Any],
    ) -> tuple[bool, Any, str]:
        """
        Try applying fixes from knowledge base.

        Returns (success, result, fix_id_used).
        """
        if not is_healable_error(str(error)):
            return False, None, ""

        if self.agent_name not in SAFE_FIX_AGENTS and not similar_fixes:
            logger.info("Agent %s not in SAFE_FIX_AGENTS — prompt-only fixes skipped", self.agent_name)

        for fix in similar_fixes:
            fix_id = fix.get("id", "")
            if fix.get("was_successful") and fix.get("success_count", 0) <= fix.get("fail_count", 0):
                continue

            started = time.perf_counter()
            try:
                success, result = self._run_with_timeout(
                    lambda f=fix: self._attempt_single_fix(
                        error, context, f, retry_fn, fix_id=f.get("id", "")
                    ),
                    FIX_ATTEMPT_TIMEOUT_SECONDS,
                )
                if success:
                    _log_fix_attempt(
                        {
                            "agent": self.agent_name,
                            "fix_id": fix_id,
                            "success": True,
                            "duration_ms": int((time.perf_counter() - started) * 1000),
                        }
                    )
                    return True, result, fix_id
            except FuturesTimeout:
                logger.warning("Fix attempt timed out for %s (fix_id=%s)", self.agent_name, fix_id)
            except Exception as exc:
                logger.warning("Fix attempt failed for %s: %s", self.agent_name, exc)

            _log_fix_attempt(
                {
                    "agent": self.agent_name,
                    "fix_id": fix_id,
                    "success": False,
                    "duration_ms": int((time.perf_counter() - started) * 1000),
                }
            )

        return False, None, ""

    @staticmethod
    def _run_with_timeout(fn: Callable[[], tuple[bool, Any]], timeout_seconds: int) -> tuple[bool, Any]:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(fn)
            return future.result(timeout=timeout_seconds)

    def _attempt_single_fix(
        self,
        error: Exception,
        context: dict[str, Any],
        fix: dict[str, Any],
        retry_fn: Callable[[], Any],
        *,
        fix_id: str,
    ) -> tuple[bool, Any]:
        solution_code = fix.get("solution_code", "")
        solution_prompt = fix.get("solution_prompt", "")

        if solution_code and self.agent_name in SAFE_FIX_AGENTS:
            success, result = self._try_code_fix(solution_code, context, retry_fn, fix_id=fix_id)
            if success:
                return True, result

        if solution_prompt:
            success, result = self._try_prompt_fix(
                error, solution_prompt, context, retry_fn, fix_id=fix_id
            )
            if success:
                return True, result

        return False, None

    def _try_code_fix(
        self,
        solution_code: str,
        context: dict[str, Any],
        retry_fn: Callable[[], Any],
        *,
        fix_id: str,
    ) -> tuple[bool, Any]:
        spec = _parse_solution_code(solution_code)
        if not spec:
            return False, None

        action = spec.get("action", "")
        params = spec.get("params") or {}

        logger.info(
            "Applying code fix action=%s agent=%s fix_id=%s (logged for audit)",
            action,
            self.agent_name,
            fix_id,
        )

        global _active_fix_context
        _active_fix_context = {**context, **params}

        try:
            if action == "pandas_read_csv_alt":
                with _pandas_read_csv_patch(params):
                    result = retry_fn()
            elif action == "matplotlib_agg":
                with _matplotlib_agg_backend():
                    result = retry_fn()
            elif action == "fuzzy_column_match":
                _active_fix_context = _apply_fuzzy_columns({**context, **params})
                result = retry_fn()
            elif action == "retry_exponential_backoff":
                import random

                delay = float(params.get("base_delay", 1.0))
                time.sleep(delay + random.uniform(0, 0.5))
                result = retry_fn()
            elif action == "context_overlay":
                _active_fix_context = {**context, **params}
                result = retry_fn()
            else:
                logger.warning("Unknown fix action: %s", action)
                return False, None

            if self._validate_fix_result(result):
                return True, result
            return False, None
        finally:
            _active_fix_context = {}

    def _try_prompt_fix(
        self,
        error: Exception,
        solution_prompt: str,
        context: dict[str, Any],
        retry_fn: Callable[[], Any],
        *,
        fix_id: str,
    ) -> tuple[bool, Any]:
        """Send solution_prompt + error to LLM, apply suggested context overlay, retry."""
        import os

        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            logger.debug("OPENAI_API_KEY not set — skipping prompt fix")
            return False, None

        try:
            from app.voice.config import LLM_MODEL
            from app.voice.openai_client import create_openai_client

            client = create_openai_client()
            user_msg = (
                f"Error: {error}\n"
                f"Context: {json.dumps(context, ensure_ascii=False, default=str)[:2000]}\n"
                f"Instructions: {solution_prompt}\n"
                "Respond with JSON: {\"action\": \"context_overlay\", \"params\": {...}} "
                "where params are safe retry hints (no code execution)."
            )
            response = client.chat.completions.create(
                model=LLM_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": "You suggest safe technical retry parameters for a data pipeline. JSON only.",
                    },
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.2,
                max_tokens=500,
            )
            content = (response.choices[0].message.content or "").strip()
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            overlay_spec = _parse_solution_code(content)
            if overlay_spec:
                return self._try_code_fix(
                    json.dumps(overlay_spec),
                    context,
                    retry_fn,
                    fix_id=fix_id,
                )
        except Exception as exc:
            logger.warning("Prompt fix LLM call failed: %s", exc)

        return False, None

    def _validate_fix_result(self, result: Any, expected_shape: str | None = None) -> bool:
        """Basic validation that fix produced usable output."""
        if result is None:
            return False
        if isinstance(result, dict):
            if expected_shape == "parser" and not result.get("data"):
                return False
            if expected_shape == "analyst" and not result.get("numeric_summary") and not result.get("text_summary"):
                return False
            return True
        return True


def get_active_fix_context() -> dict[str, Any]:
    """Return current fix overlay context (read by agents during retry)."""
    return dict(_active_fix_context)

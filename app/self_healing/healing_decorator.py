"""Self-healing decorator for agent methods."""

from __future__ import annotations

import functools
import time
import uuid
from typing import Any, Callable, TypeVar

from app.self_healing.alerts import send_self_healing_alert
from app.self_healing.config import (
    MAX_RETRY_ATTEMPTS,
    SIMILARITY_THRESHOLD,
    is_self_healing_enabled,
)
from app.self_healing.error_analyzer import (
    build_search_text,
    extract_error_signature,
    format_traceback,
)
from app.self_healing.fix_executor import FixExecutor
from app.self_healing.vector_store import get_knowledge_base
from app.utils.logger import get_logger

logger = get_logger("self_healing_decorator", "log_self_healing.json")

F = TypeVar("F", bound=Callable[..., Any])

AGENT_ERROR_TYPES = {
    "parser": "parser",
    "analyst": "analyst",
    "visualizer": "visualizer",
    "sender": "sender",
    "intent_parser": "voice",
    "formatter": "formatter",
}


def _extract_context(agent_name: str, args: tuple, kwargs: dict) -> dict[str, Any]:
    """Build healing context from call arguments."""
    ctx: dict[str, Any] = {"agent_name": agent_name}

    if agent_name == "parser":
        ctx["task_id"] = kwargs.get("task_id") or (args[0] if args else None)
        fp = kwargs.get("file_path") or (args[3] if len(args) > 3 else None)
        if fp:
            try:
                from pathlib import Path

                ctx["input_size"] = Path(fp).stat().st_size
            except OSError:
                pass
    elif agent_name in ("analyst", "visualizer", "sender"):
        data = kwargs.get("parsed") or kwargs.get("analyzed") or kwargs.get("visualized")
        if data is None and args:
            data = args[0]
        if isinstance(data, dict):
            ctx["task_id"] = data.get("task_id")
            ctx["input_size"] = data.get("row_count")
            ctx["available_columns"] = data.get("columns") or []
        prefs = kwargs.get("preferences")
        if prefs:
            ctx["preferences"] = prefs
    elif agent_name == "intent_parser":
        text = kwargs.get("text") or (args[0] if args else "")
        ctx["input_size"] = len(str(text))
        if kwargs.get("user_preferences"):
            ctx["preferences"] = kwargs["user_preferences"]
    elif agent_name == "formatter":
        data = kwargs.get("analysis_data") or (args[0] if args else None)
        if isinstance(data, dict):
            ctx["task_id"] = data.get("task_id")
            ctx["input_size"] = data.get("row_count")
        ctx["output_format"] = kwargs.get("output_format") or (args[2] if len(args) > 2 else "pdf")
        if kwargs.get("user_preferences"):
            ctx["preferences"] = kwargs["user_preferences"]

    return ctx


def with_self_healing(agent_name: str, max_retries: int | None = None) -> Callable[[F], F]:
    """
    Decorator: on exception, search ChromaDB for similar fixes and retry.

    Place above @track_agent_metrics so retries go through metrics tracking.
    """

    fix_attempts = max_retries if max_retries is not None else MAX_RETRY_ATTEMPTS

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if not is_self_healing_enabled():
                return func(*args, **kwargs)

            kb = get_knowledge_base()
            if kb is None:
                return func(*args, **kwargs)

            try:
                return func(*args, **kwargs)
            except Exception as exc:
                context = _extract_context(agent_name, args, kwargs)
                tb_str = format_traceback(exc)
                signature = extract_error_signature(
                    exc,
                    tb_str,
                    input_size=context.get("input_size"),
                )
                search_text = build_search_text(signature, tb_str)

                logger.warning(
                    "Agent %s failed — starting self-healing: %s",
                    agent_name,
                    signature.get("message", "")[:120],
                )

                similar = kb.search_similar_errors(
                    search_text,
                    agent_name=agent_name,
                    limit=3,
                    threshold=SIMILARITY_THRESHOLD,
                )

                viable = [
                    f
                    for f in similar
                    if f.get("was_successful") and f.get("success_count", 0) > f.get("fail_count", 0)
                ]

                executor = FixExecutor(agent_name)

                for attempt in range(1, fix_attempts + 1):
                    if not viable:
                        break

                    started = time.perf_counter()
                    success, result, fix_id_used = executor.attempt_fix(
                        exc,
                        context,
                        viable,
                        retry_fn=lambda: func(*args, **kwargs),
                    )
                    duration = time.perf_counter() - started
                    _record_healing_metrics(agent_name, success, duration, source="auto")

                    if success and result is not None:
                        kb.mark_fix_success(fix_id_used)
                        send_self_healing_alert(
                            agent_name=agent_name,
                            error_text=search_text[:200],
                            fix_applied=True,
                            fix_id=fix_id_used,
                        )
                        logger.info(
                            "Self-healing succeeded for %s on attempt %d (fix_id=%s)",
                            agent_name,
                            attempt,
                            fix_id_used,
                        )
                        return result

                    for fix in viable:
                        fid = fix.get("id", "")
                        if fid:
                            kb.mark_fix_failure(fid)

                new_id = kb.add_error(
                    {
                        "id": str(uuid.uuid4()),
                        "error_text": search_text,
                        "error_type": AGENT_ERROR_TYPES.get(agent_name, agent_name),
                        "agent_name": agent_name,
                        "stack_trace": tb_str,
                        "solution_prompt": "",
                        "solution_code": "",
                        "was_successful": False,
                        "success_count": 0,
                        "fail_count": 1,
                        "context": context,
                    }
                )
                send_self_healing_alert(
                    agent_name=agent_name,
                    error_text=search_text[:200],
                    fix_applied=False,
                    new_record_id=new_id,
                )
                _record_healing_metrics(agent_name, False, 0.0, source="auto")
                raise

        return wrapper  # type: ignore[return-value]

    return decorator


def _record_healing_metrics(
    agent_name: str,
    success: bool,
    duration: float,
    *,
    source: str = "auto",
) -> None:
    try:
        from app.utils.metrics import (
            knowledge_base_size,
            record_self_healing_attempt,
            self_healing_fixes_applied_total,
        )

        record_self_healing_attempt(agent_name, success, duration)
        if success:
            self_healing_fixes_applied_total.labels(source=source).inc()
        kb = get_knowledge_base()
        if kb is not None:
            knowledge_base_size.set(kb.get_stats().get("total_fixes", 0))
    except Exception as metric_exc:
        logger.debug("Could not record self-healing metrics: %s", metric_exc)

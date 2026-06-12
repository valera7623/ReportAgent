"""Celery tasks orchestrating the agent pipeline."""

from __future__ import annotations

from typing import Any

from app.agents.analyst import run_analyst
from app.agents.context_loader import get_user_preferences
from app.agents.parser import run_parser
from app.agents.sender import run_sender
from app.agents.visualizer import run_visualizer
from app.celery_app import celery_app
from app.models.schemas import AgentError
from app.utils.logger import get_logger

logger = get_logger("tasks", "log_tasks.log")


@celery_app.task(bind=True, name="tasks.generate_report")
def generate_report(
    self,
    email: str | None = None,
    sheets_url: str | None = None,
    file_path: str | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    """Run context_loader → parser → analyst → visualizer → sender pipeline."""
    task_id = self.request.id or "unknown"
    logger.info("Task %s started (email=%s)", task_id, email or "none")

    try:
        preferences = get_user_preferences(api_key)

        parsed = run_parser(
            task_id=task_id,
            email=email,
            sheets_url=sheets_url,
            file_path=file_path,
        )
        analyzed = run_analyst(parsed, preferences=preferences)
        visualized = run_visualizer(analyzed, preferences=preferences)
        result = run_sender(visualized, preferences=preferences)
        logger.info("Task %s completed successfully", task_id)
        return result

    except AgentError as exc:
        logger.error("Task %s failed in agent '%s': %s", task_id, exc.agent, exc.message)
        raise RuntimeError(f"[{exc.agent}] {exc.message}") from exc

    except Exception as exc:
        logger.exception("Task %s failed with unexpected error", task_id)
        raise

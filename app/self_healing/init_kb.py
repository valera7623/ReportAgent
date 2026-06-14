"""Initialize knowledge base and load seed fixes on startup."""

from __future__ import annotations

import json
from pathlib import Path

from app.self_healing.config import is_self_healing_enabled
from app.self_healing.vector_store import get_knowledge_base
from app.utils.logger import get_logger

logger = get_logger("self_healing_init", "log_self_healing.json")

SEED_FILE = Path(__file__).resolve().parent / "seed_fixes.json"


def init_knowledge_base() -> None:
    """Create ChromaDB collection and load seed fixes if empty."""
    if not is_self_healing_enabled():
        logger.info("Self-healing disabled — skipping knowledge base init")
        return

    kb = get_knowledge_base()
    if kb is None:
        logger.warning("Knowledge base unavailable — self-healing disabled")
        return

    stats = kb.get_stats()
    if stats["total_fixes"] > 0:
        logger.info("Knowledge base already has %d records — skipping seed", stats["total_fixes"])
        return

    if not SEED_FILE.is_file():
        logger.warning("Seed file not found: %s", SEED_FILE)
        return

    with open(SEED_FILE, encoding="utf-8") as fh:
        seeds = json.load(fh)

    count = 0
    for entry in seeds:
        try:
            kb.add_error(entry)
            count += 1
        except Exception as exc:
            logger.warning("Failed to seed fix %s: %s", entry.get("id"), exc)

    logger.info("Loaded %d seed fixes into knowledge base", count)

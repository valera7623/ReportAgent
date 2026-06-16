"""Run SQL migrations on application startup."""

from __future__ import annotations

from pathlib import Path

from app.auth.key_management import migrate_legacy_api_keys
from app.db.database import get_connection, resolve_db_path
from app.utils.logger import get_logger

logger = get_logger("init_db", "log_api.log")

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def run_migrations() -> None:
    """Create data directory and apply pending SQL migrations."""
    db_path = resolve_db_path()
    try:
        db_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.error("Cannot create database directory %s: %s", db_path.parent, exc)
        raise
    logger.info("Database path: %s", db_path)

    migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not migration_files:
        logger.warning("No migration files found in %s", MIGRATIONS_DIR)
        return

    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                filename TEXT PRIMARY KEY,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        for migration_path in migration_files:
            filename = migration_path.name
            applied = conn.execute(
                "SELECT 1 FROM schema_migrations WHERE filename = ?",
                (filename,),
            ).fetchone()
            if applied:
                continue

            sql = migration_path.read_text(encoding="utf-8")
            conn.executescript(sql)
            conn.execute(
                "INSERT INTO schema_migrations (filename) VALUES (?)",
                (filename,),
            )
            logger.info("Applied migration: %s", filename)

    migrate_legacy_api_keys()
    logger.info("Database migrations complete")

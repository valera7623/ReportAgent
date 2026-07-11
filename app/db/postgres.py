"""PostgreSQL connection helper (optional DATABASE_URL=postgresql://...)."""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Generator

_logger = logging.getLogger("postgres")


def is_postgresql_enabled() -> bool:
    url = os.getenv("DATABASE_URL", "").strip()
    return url.startswith("postgresql://") or url.startswith("postgres://")


def postgres_available() -> bool:
    if not is_postgresql_enabled():
        return False
    try:
        import psycopg2  # noqa: F401
    except ImportError:
        _logger.warning("psycopg2-binary not installed — PostgreSQL disabled")
        return False
    return True


def adapt_sql(sql: str) -> str:
    """Convert SQLite-style placeholders and functions for PostgreSQL."""
    if not is_postgresql_enabled():
        return sql
    adapted = sql.replace("?", "%s")
    adapted = adapted.replace("datetime('now')", "CURRENT_TIMESTAMP")
    adapted = adapted.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
    return adapted


@contextmanager
def get_postgres_connection() -> Generator:
    import psycopg2

    url = os.getenv("DATABASE_URL", "").strip()
    conn = psycopg2.connect(url)
    conn.autocommit = False
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

#!/usr/bin/env python3
"""
One-time Notion setup helper (bundled in Docker image).
"""

from __future__ import annotations

import os
import sys


def _title_from_rich(rich: list) -> str:
    return "".join(part.get("plain_text", "") for part in (rich or []))


def main() -> None:
    token = os.getenv("NOTION_INTEGRATION_TOKEN", "").strip()
    database_id = os.getenv("NOTION_DATABASE_ID", "").strip()
    data_source_id = os.getenv("NOTION_DATA_SOURCE_ID", "").strip()
    api_version = os.getenv("NOTION_API_VERSION", "2025-09-03")

    if not token:
        print("Set NOTION_INTEGRATION_TOKEN in .env first.")
        sys.exit(1)

    from notion_client import Client

    client = Client(auth=token, timeout_ms=30000, notion_version=api_version)

    if data_source_id:
        ds = client.request(path=f"data_sources/{data_source_id}", method="GET")
        title_prop = next(
            (n for n, m in (ds.get("properties") or {}).items() if m.get("type") == "title"),
            "Name",
        )
        print(f"OK — data source accessible (title property: {title_prop})")
        print(f"NOTION_DATA_SOURCE_ID={data_source_id}")
        return

    if database_id:
        db = client.databases.retrieve(database_id=database_id)
        title = _title_from_rich(db.get("title", []))
        print(f"OK — database '{title or '(untitled)'}' accessible")
        print(f"NOTION_DATABASE_ID={database_id}")
        data_sources = db.get("data_sources") or []
        if len(data_sources) > 1:
            print(f"\nDatabase has {len(data_sources)} data sources:")
        for ds in data_sources:
            print(f"  - {ds.get('name', '(unnamed)')} → NOTION_DATA_SOURCE_ID={ds['id']}")
        return

    print("NOTION_DATABASE_ID not set.")


if __name__ == "__main__":
    main()

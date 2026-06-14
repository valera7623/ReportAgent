#!/usr/bin/env python3
"""
One-time Notion setup helper.

1. Create integration at https://www.notion.so/my-integrations
2. Copy Internal Integration Token → NOTION_INTEGRATION_TOKEN in .env
3. Create a database in Notion, share it with the integration
4. Run this script to verify access and print database_id / data_source_id
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
        print("Create integration: https://www.notion.so/my-integrations")
        sys.exit(1)

    try:
        from notion_client import Client
    except ImportError:
        print("Install notion-client: pip install notion-client")
        sys.exit(1)

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
            print(f"\nDatabase has {len(data_sources)} data sources (multi-source API required):")
        for ds in data_sources:
            ds_title = ds.get("name") or "(unnamed)"
            print(f"  - {ds_title} → NOTION_DATA_SOURCE_ID={ds['id']}")
        if len(data_sources) == 1:
            print(f"\nRecommended .env (optional, auto-detected if omitted):")
            print(f"NOTION_DATA_SOURCE_ID={data_sources[0]['id']}")
        return

    print("NOTION_DATABASE_ID not set. Searching accessible databases...")
    search = client.search(filter={"property": "object", "value": "database"}, page_size=10)
    results = search.get("results", [])
    if not results:
        print("No databases found. Create a database in Notion and connect your integration.")
        sys.exit(1)

    for db in results:
        db_id = db["id"]
        title = _title_from_rich(db.get("title", []))
        print(f"  - {title or '(untitled)'} → NOTION_DATABASE_ID={db_id}")

    print("\nAdd NOTION_DATABASE_ID to .env and share the database with your integration.")


if __name__ == "__main__":
    main()

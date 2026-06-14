#!/usr/bin/env python3
"""
One-time Notion setup helper.

1. Create integration at https://www.notion.so/my-integrations
2. Copy Internal Integration Token → NOTION_INTEGRATION_TOKEN in .env
3. Create a database in Notion, share it with the integration
4. Run this script to verify access and print database_id
"""

from __future__ import annotations

import os
import sys


def main() -> None:
    token = os.getenv("NOTION_INTEGRATION_TOKEN", "").strip()
    database_id = os.getenv("NOTION_DATABASE_ID", "").strip()

    if not token:
        print("Set NOTION_INTEGRATION_TOKEN in .env first.")
        print("Create integration: https://www.notion.so/my-integrations")
        sys.exit(1)

    try:
        from notion_client import Client
    except ImportError:
        print("Install notion-client: pip install notion-client")
        sys.exit(1)

    client = Client(auth=token, timeout_ms=30000)

    if database_id:
        db = client.databases.retrieve(database_id=database_id)
        title = ""
        for t in db.get("title", []):
            title += t.get("plain_text", "")
        print(f"OK — database '{title}' accessible")
        print(f"NOTION_DATABASE_ID={database_id}")
        return

    print("NOTION_DATABASE_ID not set. Searching accessible databases...")
    search = client.search(filter={"property": "object", "value": "database"}, page_size=10)
    results = search.get("results", [])
    if not results:
        print("No databases found. Create a database in Notion and connect your integration.")
        sys.exit(1)

    for db in results:
        db_id = db["id"]
        title = ""
        for t in db.get("title", []):
            title += t.get("plain_text", "")
        print(f"  - {title or '(untitled)'} → NOTION_DATABASE_ID={db_id}")

    print("\nAdd NOTION_DATABASE_ID to .env and share the database with your integration.")


if __name__ == "__main__":
    main()

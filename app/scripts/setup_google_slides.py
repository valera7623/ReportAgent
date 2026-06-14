#!/usr/bin/env python3
"""
Google Slides template setup helper.

Prerequisites:
1. Google Cloud project with Slides API + Drive API enabled
2. Service account JSON key → secrets/google-sa.json
3. Create a presentation template with placeholders: %DATE%, %METRICS%, %CHART_1%
4. Share template with service account email (Editor)
5. Run this script to copy template and print GOOGLE_SLIDES_TEMPLATE_ID
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> None:
    sa_path = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "./secrets/google-sa.json")
    template_id = os.getenv("GOOGLE_SLIDES_TEMPLATE_ID", "").strip()

    path = Path(sa_path)
    if not path.is_file():
        print(f"Service account JSON not found: {path}")
        print("Create key in Google Cloud Console → IAM → Service Accounts → Keys")
        sys.exit(1)

    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
    except ImportError:
        print("Install: pip install google-auth google-api-python-client")
        sys.exit(1)

    creds = service_account.Credentials.from_service_account_file(
        str(path),
        scopes=[
            "https://www.googleapis.com/auth/presentations",
            "https://www.googleapis.com/auth/drive",
        ],
    )
    email = creds.service_account_email
    print(f"Service account: {email}")
    print("Share your template presentation with this email (Editor role).")

    if template_id:
        slides = build("slides", "v1", credentials=creds, cache_discovery=False)
        pres = slides.presentations().get(presentationId=template_id).execute()
        print(f"OK — template '{pres.get('title')}' accessible")
        print(f"GOOGLE_SLIDES_TEMPLATE_ID={template_id}")
        return

    print("\nGOOGLE_SLIDES_TEMPLATE_ID not set.")
    print("Steps:")
    print("  1. Create Google Slides with placeholders %DATE%, %METRICS%, %CHART_1%")
    print("  2. Share with service account email above")
    print("  3. Copy presentation ID from URL:")
    print("     https://docs.google.com/presentation/d/PRESENTATION_ID/edit")
    print("  4. Set GOOGLE_SLIDES_TEMPLATE_ID=PRESENTATION_ID in .env")


if __name__ == "__main__":
    main()

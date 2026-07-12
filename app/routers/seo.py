"""SEO static files: robots.txt and sitemap.xml at site root."""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, Response

router = APIRouter(tags=["seo"])

_FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"

_PUBLIC_PATHS = [
    "/",
    "/help/",
    "/app/",
    "/app/#/login",
    "/app/#/register",
    "/app/#/pricing",
    "/app/#/pricing-yookassa",
    "/app/#/reset-password",
]


def _site_base() -> str:
    domain = (os.getenv("DOMAIN") or os.getenv("SITE_URL") or "reportagent.example.com").strip()
    domain = domain.rstrip("/")
    if domain.startswith("http://") or domain.startswith("https://"):
        return domain.rstrip("/")
    return f"https://{domain}"


@router.get("/robots.txt", include_in_schema=False)
async def robots_txt() -> Response:
    static = _FRONTEND_DIR / "robots.txt"
    if static.is_file():
        body = static.read_text(encoding="utf-8")
        body = body.replace("https://reportagent.example.com", _site_base())
        return Response(content=body, media_type="text/plain; charset=utf-8")
    return Response(
        content=f"User-agent: *\nAllow: /\nSitemap: {_site_base()}/sitemap.xml\n",
        media_type="text/plain; charset=utf-8",
    )


@router.get("/sitemap.xml", include_in_schema=False)
async def sitemap_xml() -> Response:
    static = _FRONTEND_DIR / "sitemap.xml"
    today = date.today().isoformat()
    base = _site_base()

    if static.is_file():
        body = static.read_text(encoding="utf-8")
        body = body.replace("https://reportagent.example.com", base)
        if "<lastmod>" in body:
            import re

            body = re.sub(r"<lastmod>[^<]+</lastmod>", f"<lastmod>{today}</lastmod>", body)
        return Response(content=body, media_type="application/xml; charset=utf-8")

    urls = "\n".join(
        f"""  <url>
    <loc>{base}{path}</loc>
    <lastmod>{today}</lastmod>
    <changefreq>weekly</changefreq>
    <priority>{"1.0" if i == 0 else "0.8"}</priority>
  </url>"""
        for i, path in enumerate(_PUBLIC_PATHS)
    )
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{urls}
</urlset>
"""
    return Response(content=xml, media_type="application/xml; charset=utf-8")


@router.get("/app/robots.txt", include_in_schema=False)
async def app_robots_txt() -> FileResponse:
    return FileResponse(_FRONTEND_DIR / "robots.txt", media_type="text/plain; charset=utf-8")

#!/usr/bin/env python3
"""Build favicon + og-image from frontend/assets/* source files (requires Pillow)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "frontend"
ASSETS = ROOT / "assets"


def main() -> int:
    try:
        from PIL import Image
    except ImportError:
        print("ERROR: Pillow required. pip install pillow", file=sys.stderr)
        return 1

    logo_src = ASSETS / "logo.png"
    fav_src = ASSETS / "favicon-source.png"
    if not fav_src.is_file():
        print(f"ERROR: missing {fav_src}", file=sys.stderr)
        return 1

    ASSETS.mkdir(parents=True, exist_ok=True)
    fav = Image.open(fav_src).convert("RGBA")

    def square_icon(src: Image.Image, size: int) -> Image.Image:
        img = src.copy()
        img.thumbnail((size, size), Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        canvas.paste(img, ((size - img.width) // 2, (size - img.height) // 2), img)
        return canvas

    for size in (16, 32):
        square_icon(fav, size).save(ROOT / f"favicon-{size}x{size}.png", optimize=True)
    square_icon(fav, 180).save(ROOT / "apple-touch-icon.png", optimize=True)
    square_icon(fav, 512).save(ROOT / "favicon-512.png", optimize=True)
    Image.open(ROOT / "favicon-16x16.png").save(
        ROOT / "favicon.ico", format="ICO", sizes=[(16, 16), (32, 32)]
    )

    if logo_src.is_file():
        logo = Image.open(logo_src).convert("RGBA")
        logo.thumbnail((420, 72), Image.Resampling.LANCZOS)
        logo.save(ASSETS / "logo-sidebar.png", optimize=True)
        og = Image.new("RGBA", (1200, 630), (15, 23, 42, 255))
        logo_og = Image.open(logo_src).convert("RGBA")
        logo_og.thumbnail((900, 400), Image.Resampling.LANCZOS)
        og.paste(logo_og, ((1200 - logo_og.width) // 2, (630 - logo_og.height) // 2), logo_og)
        og.convert("RGB").save(ROOT / "og-image.png", optimize=True)

    print(f"Brand assets updated in {ROOT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

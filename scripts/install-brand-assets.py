#!/usr/bin/env python3
"""Build favicon + og-image from frontend/assets/* source files (requires Pillow)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "frontend"
ASSETS = ROOT / "assets"


def crop_logo_padding(im, threshold: int = 32, pad: int = 4):
    from PIL import Image

    rgba = im.convert("RGBA")
    w, h = rgba.size
    pixels = rgba.load()
    min_x, min_y, max_x, max_y = w, h, 0, 0
    found = False
    for y in range(h):
        for x in range(w):
            r, g, b, a = pixels[x, y]
            if a < 16:
                continue
            if r <= threshold and g <= threshold and b <= threshold:
                continue
            found = True
            min_x = min(min_x, x)
            min_y = min(min_y, y)
            max_x = max(max_x, x)
            max_y = max(max_y, y)
    if not found:
        return rgba
    min_x = max(0, min_x - pad)
    min_y = max(0, min_y - pad)
    max_x = min(w - 1, max_x + pad)
    max_y = min(h - 1, max_y + pad)
    return rgba.crop((min_x, min_y, max_x + 1, max_y + 1))


def prepare_logo() -> Path:
    from PIL import Image

    original = ASSETS / "logo-original.png"
    if not original.is_file():
        original = ASSETS / "logo.png"
    if not original.is_file():
        raise FileNotFoundError("logo-original.png or logo.png missing")

    cropped = crop_logo_padding(Image.open(original))
    cropped.save(ASSETS / "logo.png", optimize=True)

    sidebar = cropped.copy()
    sidebar.thumbnail((520, 88), Image.Resampling.LANCZOS)
    sidebar.save(ASSETS / "logo-sidebar.png", optimize=True)
    return ASSETS / "logo.png"


def main() -> int:
    try:
        from PIL import Image
    except ImportError:
        print("ERROR: Pillow required. pip install pillow", file=sys.stderr)
        return 1

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

    try:
        logo_path = prepare_logo()
    except FileNotFoundError as exc:
        print(f"WARNING: {exc}", file=sys.stderr)
        logo_path = ASSETS / "logo.png"

    if logo_path.is_file():
        og = Image.new("RGBA", (1200, 630), (15, 23, 42, 255))
        logo_og = Image.open(logo_path).convert("RGBA")
        logo_og.thumbnail((920, 120), Image.Resampling.LANCZOS)
        og.paste(logo_og, ((1200 - logo_og.width) // 2, (630 - logo_og.height) // 2), logo_og)
        og.convert("RGB").save(ROOT / "og-image.png", optimize=True)

    print(f"Brand assets updated in {ROOT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

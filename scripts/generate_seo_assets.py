#!/usr/bin/env python3
"""Generate favicon and OG image for ReportAgent (stdlib only, no Pillow)."""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "frontend"


def _chunk(tag: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)


def write_png(path: Path, width: int, height: int, rgba_fn) -> None:
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        for x in range(width):
            r, g, b, a = rgba_fn(x, y, width, height)
            raw.extend((r, g, b, a))

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n"
    png += _chunk(b"IHDR", ihdr)
    png += _chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    png += _chunk(b"IEND", b"")
    path.write_bytes(png)


def brand_gradient(x: int, y: int, w: int, h: int) -> tuple[int, int, int, int]:
    t = (x / max(w - 1, 1) + y / max(h - 1, 1)) / 2
    r = int(37 + t * (99 - 37))
    g = int(99 + t * (102 - 99))
    b = int(235 + t * (241 - 235))
    return r, g, b, 255


def draw_shield(cx: int, cy: int, size: int, color: tuple[int, int, int, int]) -> None:
    pass  # placeholder for future vector draw


def icon_rgba(x: int, y: int, w: int, h: int) -> tuple[int, int, int, int]:
    r, g, b, a = brand_gradient(x, y, w, h)
    cx, cy = w // 2, h // 2
    dx, dy = x - cx, y - cy
    if dx * dx + dy * dy < (min(w, h) * 0.32) ** 2:
        return 255, 255, 255, 255
    if abs(dx) < w * 0.12 and cy - h * 0.15 < y < cy + h * 0.28:
        return 255, 255, 255, 255
    return r, g, b, a


def og_rgba(x: int, y: int, w: int, h: int) -> tuple[int, int, int, int]:
    r, g, b, a = brand_gradient(x, y, w, h)
    if y > h * 0.55 and x < w * 0.7:
        return min(255, r + 20), min(255, g + 20), min(255, b + 30), 255
    return r, g, b, a


def write_ico(path: Path, sizes: list[int]) -> None:
    images: list[tuple[int, bytes]] = []
    for size in sizes:
        raw = bytearray()
        for y in range(size):
            for x in range(size):
                r, g, b, _a = icon_rgba(x, y, size, size)
                raw.extend((b, g, r, 0))
        images.append((size, bytes(raw)))

    offset = 6 + 16 * len(images)
    out = bytearray()
    out += struct.pack("<HHH", 0, 1, len(images))
    for size, _ in images:
        dim = 0 if size >= 256 else size
        out += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(images[0][1]), offset)
        offset += len(images[0][1])

    for size, data in images:
        bih = struct.pack(
            "<IIIHHIIIIII",
            40,
            size,
            size * 2,
            1,
            32,
            0,
            len(data),
            0,
            0,
            0,
            0,
        )
        out += bih + data

    path.write_bytes(bytes(out))


def main() -> None:
    brand_source = ROOT / "assets" / "favicon-source.png"
    if brand_source.is_file() and (ROOT / "favicon.ico").is_file():
        print(f"Brand favicons present ({brand_source.name}); skipping procedural generation")
        return

    ROOT.mkdir(parents=True, exist_ok=True)
    for size in (16, 32, 180):
        write_png(ROOT / f"favicon-{size}x{size}.png", size, size, icon_rgba)
    write_ico(ROOT / "favicon.ico", [16, 32])
    write_png(ROOT / "apple-touch-icon.png", 180, 180, icon_rgba)
    write_png(ROOT / "og-image.png", 1200, 630, og_rgba)
    print(f"SEO assets written to {ROOT}")


if __name__ == "__main__":
    main()

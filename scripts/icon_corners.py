#!/usr/bin/env python3
"""
BitcoinTX's Mac icon with nothing painted outside its rounded square (#680):
its corners were painted white, which showed on a dark Dock or Finder window.

Rewrites desktop/resources/icon.icns: the white joined to each corner of its
1024-pixel image becomes transparent, the square's edge keeps its own
anti-aliasing (the colour just inside it, partly transparent), and every
smaller size is made from that image, resized with its transparency taken
into account so no white comes back at the edge. An icon already transparent
there comes out the same. Then make the Preview's icon from it again
(scripts/preview_icon.py). Needs a Mac (iconutil) and Pillow (the backend's):

    .venv/bin/python scripts/icon_corners.py && .venv/bin/python scripts/preview_icon.py
"""

import subprocess
import tempfile
from collections import deque
from pathlib import Path

from PIL import Image

ICON = Path(__file__).resolve().parents[1] / "desktop" / "resources" / "icon.icns"
# Each image iconutil packs, and its size in pixels
SIZES = {"16x16": 16, "16x16@2x": 32, "32x32": 32, "32x32@2x": 64, "128x128": 128, "128x128@2x": 256,
         "256x256": 256, "256x256@2x": 512, "512x512": 512, "512x512@2x": 1024}
# Paint at least this light in every channel is the white around the square
WHITE = 200
# How far in from an edge pixel its own colour is read, in pixels at 1024
INWARD = 3


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        iconset = Path(tmp) / "icon.iconset"
        subprocess.run(["iconutil", "-c", "iconset", str(ICON), "-o", str(iconset)], check=True)
        icon = without_corners(Image.open(iconset / "icon_512x512@2x.png").convert("RGBA"))
        for name, px in SIZES.items():
            sized = icon if px == icon.width else icon.convert("RGBa").resize((px, px), Image.LANCZOS).convert("RGBA")
            sized.save(iconset / f"icon_{name}.png")
        subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(ICON)], check=True)


def without_corners(icon: Image.Image) -> Image.Image:
    """The icon with the white joined to its corners transparent, and the
    pixels along that white the colour just inside them, as transparent as
    they were white."""
    out = icon.copy()
    pixels, size = out.load(), out.width
    outside = _white_from_the_corners(pixels, size)
    for x, y in outside:
        pixels[x, y] = (0, 0, 0, 0)
    for x, y in _along(outside, size):
        within = _inward(pixels, size, x, y)
        pixels[x, y] = (*within[:3], round(255 * _cover(icon.getpixel((x, y)), within)))
    return out


def _white_from_the_corners(pixels, size: int) -> set[tuple[int, int]]:
    """Every white pixel reached from a corner through white ones."""
    corners = [(0, 0), (size - 1, 0), (0, size - 1), (size - 1, size - 1)]
    seen, queue = set(), deque(c for c in corners if min(pixels[c][:3]) >= WHITE)
    seen.update(queue)
    while queue:
        x, y = queue.popleft()
        for near in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if near not in seen and 0 <= near[0] < size and 0 <= near[1] < size and min(pixels[near][:3]) >= WHITE:
                seen.add(near)
                queue.append(near)
    return seen


def _along(outside: set[tuple[int, int]], size: int) -> set[tuple[int, int]]:
    """The pixels of the square touching the white: its edge, part white."""
    return {(x + dx, y + dy) for x, y in outside for dx in (-1, 0, 1) for dy in (-1, 0, 1)
            if 0 <= x + dx < size and 0 <= y + dy < size and (x + dx, y + dy) not in outside}


def _inward(pixels, size: int, x: int, y: int) -> tuple[int, ...]:
    """The colour INWARD pixels in from (x, y), towards the icon's middle."""
    middle = (size - 1) / 2
    dx, dy = middle - x, middle - y
    length = (dx * dx + dy * dy) ** 0.5
    return pixels[round(x + INWARD * dx / length), round(y + INWARD * dy / length)]


def _cover(edge: tuple[int, ...], within: tuple[int, ...]) -> float:
    """How much of an edge pixel is the square's own colour rather than white,
    from 0 to 1: what it is, between white and the colour just inside it."""
    shares = [(255 - e) / (255 - w) for e, w in zip(edge[:3], within[:3], strict=True) if 255 - w > 20]
    return min(1.0, max(0.0, sum(shares) / len(shares))) if shares else 1.0


if __name__ == "__main__":
    main()

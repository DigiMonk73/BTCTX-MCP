#!/usr/bin/env python3
"""
BitcoinTX Preview's icon (#670): BitcoinTX's own with a red "PREVIEW" band
across its lower part, so the pre-release app (2.0's alphas and betas) can't
be taken for BitcoinTX in the Dock, Launchpad, the app switcher or Finder.
At 16 and 32 pixels the band carries no word, which would only blur there:
the stripe alone tells the two apart.

desktop/resources/icon-preview.icns is checked in, made by this script from
desktop/resources/icon.icns: run it again whenever that one changes. It needs
a Mac (iconutil and the system's Arial Bold) and Pillow (the backend's):

    .venv/bin/python scripts/preview_icon.py
"""

import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

RESOURCES = Path(__file__).resolve().parents[1] / "desktop" / "resources"
FONT = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
WORD = "PREVIEW"
# The band's top and bottom, as fractions of the icon's height: across the
# coin's lower half, clear of the rounded corners
BAND = (0.66, 0.86)
RED = (217, 45, 32)  # white on it: 4.8 to 1
# Each image iconutil packs, and its size in pixels
SIZES = {"16x16": 16, "16x16@2x": 32, "32x32": 32, "32x32@2x": 64, "128x128": 128, "128x128@2x": 256,
         "256x256": 256, "256x256@2x": 512, "512x512": 512, "512x512@2x": 1024}
SMALLEST_WITH_WORD = 64


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        plain, preview = Path(tmp) / "plain.iconset", Path(tmp) / "preview.iconset"
        subprocess.run(["iconutil", "-c", "iconset", str(RESOURCES / "icon.icns"), "-o", str(plain)], check=True)
        icon = Image.open(plain / "icon_512x512@2x.png").convert("RGBA")
        with_word, stripe = banded(icon, word=True), banded(icon, word=False)
        preview.mkdir()
        for name, px in SIZES.items():
            source = with_word if px >= SMALLEST_WITH_WORD else stripe
            source.resize((px, px), Image.LANCZOS).save(preview / f"icon_{name}.png")
        subprocess.run(["iconutil", "-c", "icns", str(preview), "-o", str(RESOURCES / "icon-preview.icns")],
                       check=True)


def banded(icon: Image.Image, word: bool) -> Image.Image:
    """The icon with the band across it, a darker line along each edge so it
    stands off the gold, and the word on it."""
    out = icon.copy()
    draw = ImageDraw.Draw(out)
    size = out.width
    top, bottom = round(BAND[0] * size), round(BAND[1] * size)
    edge = max(1, round(0.008 * size))
    shade = tuple(round(c * 0.55) for c in RED)
    draw.rectangle([0, top, size, bottom], fill=RED)
    draw.rectangle([0, top, size, top + edge], fill=shade)
    draw.rectangle([0, bottom - edge, size, bottom], fill=shade)
    if word:
        _write_word(draw, size, top, bottom)
    return out


def _write_word(draw: ImageDraw.ImageDraw, size: int, top: int, bottom: int) -> None:
    """WORD in white capitals, slightly spaced, centred on the band."""
    font = ImageFont.truetype(FONT, round((bottom - top) * 0.62))
    gap = round(font.size * 0.08)
    widths = [draw.textlength(letter, font=font) for letter in WORD]
    x = (size - sum(widths) - gap * (len(WORD) - 1)) / 2
    _, cap_top, _, cap_bottom = font.getbbox(WORD)
    y = (top + bottom) / 2 - (cap_bottom - cap_top) / 2 - cap_top
    for letter, width in zip(WORD, widths, strict=True):
        draw.text((x, y), letter, font=font, fill=(255, 255, 255))
        x += width + gap


if __name__ == "__main__":
    main()

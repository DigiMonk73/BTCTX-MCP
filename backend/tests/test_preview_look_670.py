"""
BitcoinTX Preview looks like a test version, never like BitcoinTX (#670).

BitcoinTX Preview, the Mac app of 2.0's pre-releases, runs beside BitcoinTX
with its own folders and port. Its icon is BitcoinTX's with a "PREVIEW" band
(desktop/resources/icon-preview.icns, made by scripts/preview_icon.py), and
its executable takes the app's own name, which crash reports, Console and ps
show. A release keeps BitcoinTX's icon and executable. The banner on every
page and the Preview's first-page line are the frontend's
(PrereleaseBanner.tsx, ChooseOwnLogin.tsx).

Both icons' corners, outside the rounded square, are transparent at every
size (#680): painted white, they showed on a dark Dock.
"""

import importlib.util
import io
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
DESKTOP = ROOT / "desktop"
sys.path.insert(0, str(DESKTOP))
import desktop_paths  # noqa: E402

# The band scripts/preview_icon.py draws: where, and its red
_spec = importlib.util.spec_from_file_location("preview_icon", ROOT / "scripts" / "preview_icon.py")
preview_icon = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(preview_icon)
BAND, RED = preview_icon.BAND, preview_icon.RED
# What cuts the icon's corners (#680)
_spec = importlib.util.spec_from_file_location("icon_corners", ROOT / "scripts" / "icon_corners.py")
icon_corners = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(icon_corners)

RESOURCES = DESKTOP / "resources"
SPEC = (DESKTOP / "BitcoinTX.spec").read_text()


def version(monkeypatch, value: str) -> None:
    monkeypatch.setattr(desktop_paths, "app_version", lambda: value)


@pytest.mark.parametrize("value, icon", [
    ("2.0.0-alpha.2", "icon-preview.icns"), ("2.0.0-beta.1", "icon-preview.icns"),
    ("2.0.0", "icon.icns"), ("1.2.10", "icon.icns"),
])
def test_the_preview_takes_the_banded_icon_and_a_release_bitcointxs(monkeypatch, value, icon):
    version(monkeypatch, value)
    assert desktop_paths.icon_name() == icon


def test_the_spec_takes_the_icon_and_the_executables_name_from_desktop_paths():
    assert "from desktop_paths import bundle_id, icon_name, own_name" in SPEC
    assert 'ICON = SPEC_DIR / "resources" / icon_name()' in SPEC
    assert "icon=str(ICON)" in SPEC
    # the executable is named after the app: "BitcoinTX Preview" in a crash report, never "BitcoinTX"
    assert re.search(r"exe = EXE\((?:.|\n)*?name=APP_NAME,", SPEC)
    assert re.search(r"coll = COLLECT\((?:.|\n)*?name=APP_NAME,", SPEC)
    assert 'name="BitcoinTX"' not in SPEC and '"icon.icns"' not in SPEC


def _largest(path: Path) -> Image.Image:
    with Image.open(path) as icns:
        return icns.convert("RGB")


def test_the_preview_icon_is_bitcointxs_with_a_red_band():
    """Made from BitcoinTX's icon, so it is still recognised: the same above
    the band, red across it (the word is white on red there)."""
    plain, preview = _largest(RESOURCES / "icon.icns"), _largest(RESOURCES / "icon-preview.icns")
    assert plain.size == preview.size == (1024, 1024)
    top = round(BAND[0] * 1024)
    assert preview.crop((0, 0, 1024, top - 8)).tobytes() == plain.crop((0, 0, 1024, top - 8)).tobytes()
    middle = round(sum(BAND) / 2 * 1024)
    for x in (12, 1011):  # the band's ends, left and right of the word
        assert preview.getpixel((x, middle)) == RED
    assert plain.getpixel((12, middle)) != RED
    # The lower corners reach into the band's ends: they stay transparent (#680)
    for x in (0, 1023):
        assert _alpha(RESOURCES / "icon.icns", (x, 870)) == _alpha(RESOURCES / "icon-preview.icns", (x, 870)) == 0


def _alpha(path: Path, xy: tuple[int, int]) -> int:
    with Image.open(path) as icns:
        return icns.convert("RGBA").getpixel(xy)[3]


# Every image macOS picks from: 16 and 32 pixels (Finder's list view), up to 1024
IMAGES = {"ic04": 16, "ic05": 32, "ic11": 32, "ic12": 64, "ic07": 128, "ic13": 256, "ic08": 256, "ic14": 512,
          "ic09": 512, "ic10": 1024}


def _images(path: Path) -> dict[str, Image.Image]:
    data, images, at = path.read_bytes(), {}, 8
    while at < len(data):
        kind, length = data[at:at + 4].decode("latin-1"), int.from_bytes(data[at + 4:at + 8], "big")
        body = data[at + 8:at + length]
        if kind in IMAGES:
            images[kind] = _argb(body, IMAGES[kind]) if body.startswith(b"ARGB") else Image.open(io.BytesIO(body))
        at += length
    return images


def _argb(body: bytes, px: int) -> Image.Image:
    """An ARGB image (ic04, ic05): its four channels one after another, run-length coded."""
    out, at = bytearray(), 4
    while len(out) < 4 * px * px:
        n = body[at]
        if n & 0x80:
            out += body[at + 1:at + 2] * (n - 125)
            at += 2
        else:
            out += body[at + 1:at + 2 + n]
            at += n + 2
    channels = [bytes(out[k * px * px:(k + 1) * px * px]) for k in (1, 2, 3, 0)]
    return Image.merge("RGBA", [Image.frombytes("L", (px, px), c) for c in channels])


def test_every_size_of_the_preview_icon_shows_the_band():
    """Finder's list view (16 and 32 pixels) included, where only the stripe is drawn."""
    images = _images(RESOURCES / "icon-preview.icns")
    assert set(images) == set(IMAGES)
    for kind, image in images.items():
        assert image.size == (IMAGES[kind], IMAGES[kind])
        red = image.convert("RGB").getpixel((1, round(sum(BAND) / 2 * image.height)))
        assert red[0] > 150 and red[1] < 90 and red[2] < 80, (kind, red)
    plain = _images(RESOURCES / "icon.icns")["ic04"].getpixel((1, round(sum(BAND) / 2 * 16)))
    assert not (plain[0] > 150 and plain[1] < 90), plain


@pytest.mark.parametrize("icon", ["icon.icns", "icon-preview.icns"])
def test_both_icons_have_transparent_corners_at_every_size(icon):
    """Outside the rounded square nothing is painted, so a dark Dock or Finder
    window shows through, never a white square (#680); inside, it's opaque."""
    images = _images(RESOURCES / icon)
    assert set(images) == set(IMAGES)
    for kind, image in images.items():
        rgba, last = image.convert("RGBA"), image.width - 1
        # Each corner (its arc's radius is about 17% of the side) and a little
        # along its sides; inside, the middles of the sides and the centre
        outside = [(0, 0), (last, 0), (0, last), (last, last)]
        if image.width >= 64:  # smaller, the corner is a pixel or two
            tip = round(0.03 * image.width)
            outside += [(tip, 0), (0, tip), (last - tip, last), (last, last - tip)]
        inside = [(image.width // 2, 0), (0, image.height // 2), (last, image.height // 2),
                  (image.width // 2, last), (image.width // 2, image.height // 2)]
        # At 16 and 32 pixels a corner pixel is partly the curve, drawn faintly (under a tenth)
        faint = 0 if image.width >= 64 else 24
        assert all(rgba.getpixel(xy)[3] <= faint for xy in outside), (kind, [rgba.getpixel(xy) for xy in outside])
        # Along the cut, the edge is the square's own colour: no light line left round it that
        # shows (a resized edge also holds pixels almost clear, whose colour rounds to anything)
        light_edge = [p for p in rgba.get_flattened_data() if 24 < p[3] < 255 and min(p[:3]) >= icon_corners.WHITE]
        assert not light_edge, (kind, light_edge[:5])
        assert [rgba.getpixel(xy)[3] for xy in inside] == [255] * len(inside), (kind, image.size)


def test_the_corner_script_cuts_only_opaque_white():
    """A square on white: the white joined to its corners goes, the square
    stays; cut again, with white left under its clear pixels (as iconutil
    keeps it), it comes out the same (#680's review)."""
    icon = Image.new("RGBA", (64, 64), (255, 255, 255, 255))
    ImageDraw.Draw(icon).rounded_rectangle([0, 0, 63, 63], 12, fill=(30, 50, 90, 255))
    cut = icon_corners.without_corners(icon)
    assert [cut.getpixel(xy)[3] for xy in [(0, 0), (63, 0), (0, 63), (63, 63)]] == [0, 0, 0, 0]
    assert [cut.getpixel(xy)[3] for xy in [(32, 0), (0, 32), (32, 32)]] == [255, 255, 255]
    clear = Image.new("RGBA", cut.size, (255, 255, 255, 0))
    clear.paste(cut, mask=cut.getchannel("A").point(lambda a: 255 if a else 0))
    assert icon_corners.without_corners(clear).tobytes() == clear.tobytes()


on_a_mac = pytest.mark.skipif(sys.platform != "darwin", reason="PlistBuddy, macOS's")


def _app(tmp_path: Path, executable: str, plist: bool) -> Path:
    """An "app" whose binary writes down that it ran."""
    app = tmp_path / "Fake.app"
    binary = app / "Contents" / "MacOS" / executable
    binary.parent.mkdir(parents=True)
    binary.write_text('#!/bin/sh\necho ran > "$RAN"\n')
    binary.chmod(0o755)
    if plist:
        (app / "Contents" / "Info.plist").write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n<plist version="1.0"><dict>'
            f"<key>CFBundleExecutable</key><string>{executable}</string></dict></plist>\n")
    return app


def _run(tmp_path: Path, app: Path) -> subprocess.CompletedProcess:
    """The script in a test home; without --fresh it asks no port."""
    env = {**os.environ, "HOME": str(tmp_path), "TMPDIR": str(tmp_path / "tmp"), "RAN": str(tmp_path / "ran")}
    env.pop("BTCTX_TEST_DATA_DIR", None)
    return subprocess.run(["bash", str(DESKTOP / "run-test-build.sh"), "--app", str(app)], env=env,
                          capture_output=True, text=True, timeout=60)


@on_a_mac
def test_a_test_run_starts_the_executable_its_bundle_names(tmp_path):
    made = _run(tmp_path, _app(tmp_path, "BitcoinTX Preview", plist=True))
    assert made.returncode == 0, made.stderr
    assert (tmp_path / "ran").read_text() == "ran\n"


def test_a_test_run_of_a_bundle_that_names_none_starts_bitcointx(tmp_path):
    """Every build before #670 is named BitcoinTX; so is a bundle that doesn't say."""
    made = _run(tmp_path, _app(tmp_path, "BitcoinTX", plist=False))
    assert made.returncode == 0, made.stderr
    assert (tmp_path / "ran").read_text() == "ran\n"

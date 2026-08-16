#!/usr/bin/env python3
"""Composite the raw simulator screenshots into an iPhone 16 Pro device frame.

The raw shots in assets/screens are 1206x2622 (iPhone 16 Pro @3x). The frame PNG
has a transparent screen aperture at (102, 100)-(1307, 2721) — exactly 1206x2622 —
so each shot drops straight in with no scaling. The screenshot goes *behind* the
frame, which is what keeps the rounded screen corners and the Dynamic Island right,
and it is clipped to the device silhouette so its square corners cannot poke out
past the rounded bezel.

The frame itself is downloaded on demand and cached (gitignored) rather than kept
in the repo as a source asset.

The one screen that cannot be composited ahead of time is the `<video>` in the
core-loop section, so this also writes assets/img/device-frame.png — the bezel
with its aperture left transparent — which the page lays *over* the playing
video. `.device-frame` in css/styles.css positions the video using the same
aperture numbers, expressed as percentages of the frame:

    left   102/1406    top     100/2822
    width 1206/1406    height 2622/2822

    python3 tools/frame-screens.py
"""
from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "assets" / "screens"
OUT = SRC / "framed"
OVERLAY = ROOT / "assets" / "img" / "device-frame.png"
CACHE = ROOT / "tools" / ".cache"
FRAME = CACHE / "iphone-16-pro-black-titanium.png"
FRAME_URL = (
    "https://raw.githubusercontent.com/jamesjingyi/mockup-device-frames/main/"
    "Exports/iOS/16%20Pro/16%20Pro%20-%20Black%20Titanium.png"
)

# Transparent screen aperture inside the frame, measured from its alpha channel.
APERTURE = (102, 100)
SCREEN_SIZE = (1206, 2622)


def load_frame() -> Image.Image:
    if not FRAME.exists():
        CACHE.mkdir(parents=True, exist_ok=True)
        print(f"downloading device frame -> {FRAME}")
        urllib.request.urlretrieve(FRAME_URL, FRAME)
    return Image.open(FRAME).convert("RGBA")


def body_mask(frame: Image.Image) -> Image.Image:
    """Everything enclosed by the device silhouette — the bezel plus the aperture.

    Flood-filling the transparent background in from a corner leaves the screen
    aperture (transparent, but not reachable from outside) as the only hole.
    """
    filled = frame.getchannel("A").point(lambda v: 255 if v > 0 else 0)
    ImageDraw.floodfill(filled, (0, 0), 128)
    return filled.point(lambda v: 0 if v == 128 else 255)


def zero_transparent(canvas: Image.Image) -> Image.Image:
    """Zero the colour of fully transparent pixels.

    Browsers honour alpha, but viewers and thumbnailers that ignore it otherwise
    show the leftover colour as square corners around the device.
    """
    alpha = canvas.getchannel("A")
    opaque = alpha.point(lambda v: 255 if v > 0 else 0)
    return Image.merge(
        "RGBA",
        [ImageChops.multiply(ch, opaque) for ch in canvas.split()[:3]] + [alpha],
    )


def main() -> int:
    frame = load_frame()
    mask = body_mask(frame)
    OUT.mkdir(parents=True, exist_ok=True)

    zero_transparent(frame).save(OVERLAY, optimize=True)
    print(f"bezel overlay -> {OVERLAY.relative_to(ROOT)}")

    shots = sorted(p for p in SRC.glob("*.png") if p.is_file())
    if not shots:
        print(f"no screenshots in {SRC}", file=sys.stderr)
        return 1

    for shot in shots:
        screen = Image.open(shot).convert("RGBA")
        if screen.size != SCREEN_SIZE:
            print(f"  {shot.name}: {screen.size} -> resizing to {SCREEN_SIZE}")
            screen = screen.resize(SCREEN_SIZE, Image.LANCZOS)

        canvas = Image.new("RGBA", frame.size, (0, 0, 0, 0))
        canvas.paste(screen, APERTURE)
        canvas.putalpha(ImageChops.multiply(canvas.getchannel("A"), mask))
        canvas.alpha_composite(frame)

        canvas = zero_transparent(canvas)

        dest = OUT / shot.name
        canvas.save(dest, optimize=True)
        print(f"framed {shot.name} -> {dest.relative_to(ROOT)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

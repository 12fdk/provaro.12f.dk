#!/usr/bin/env python3
"""Composite the raw simulator screenshots into their device frame.

Two devices, one path. The raw shots under assets/screens/<device> are exactly
the size of the transparent screen aperture in that device's frame PNG, so each
shot drops straight in with no scaling:

    iphone  1206x2622 (iPhone 16 Pro @3x)      frame 1406x2822, aperture at (102, 100)
    ipad    2064x2752 (iPad Pro 13" M4 @2x)    frame 2264x2952, aperture at (100, 100)

The screenshot goes *behind* the frame, which is what keeps the rounded screen
corners and the Dynamic Island right, and it is clipped to the device silhouette
so its square corners cannot poke out past the rounded bezel.

The frames themselves are downloaded on demand and cached (gitignored) rather
than kept in the repo as source assets.

The one screen that cannot be composited ahead of time is the `<video>` in the
core-loop section, so this also writes assets/img/device-frame*.png — the bezel
with its aperture left transparent — which the page lays *over* the playing
video. `.reel-frame` in css/styles.css positions the video using the same
aperture numbers, expressed as percentages of the frame.

Output is downscaled on the way out (see MAX_W below). The frames are 1406 and
2264 pixels wide and the page renders them at 176-430 CSS pixels, so shipping
them at full resolution costs megabytes that no display can spend.

**Output is WebP, not PNG** (#17). These are photographs inside a device
silhouette, which is the case PNG is worst at and WebP-with-alpha is best at:
the same iPhone mark-up shot is 605K as PNG and 46K at q82. It matters more
than the file sizes suggest, because a browser fetches a `loading="lazy"` image
that is `display: none`, so every visitor downloads the device set they never
switch to. QUALITY was checked, not assumed — at 2x the asset's own size the
app's own UI text is indistinguishable from the PNG.

    python3 tools/frame-screens.py
"""
from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "assets" / "screens"
CACHE = ROOT / "tools" / ".cache"
BASE_URL = "https://raw.githubusercontent.com/jamesjingyi/mockup-device-frames/main/Exports/"

# Widest the page ever renders these, times a comfortable factor for high-DPR
# screens: framed shots peak at 264 CSS px in a step, the bezel at 430 in the reel.
MAX_W = {"shot": 800, "bezel": 1200}

# q82 with alpha kept near-lossless: the alpha channel is the device silhouette,
# and artefacts there show up as a fringe against the page rather than as noise
# inside a photograph.
QUALITY = 82
ALPHA_QUALITY = 100

DEVICES = {
    "iphone": {
        "frame": CACHE / "iphone-16-pro-black-titanium.png",
        "url": BASE_URL + "iOS/16%20Pro/16%20Pro%20-%20Black%20Titanium.png",
        "aperture": (102, 100),
        "screen": (1206, 2622),
        # Named without a suffix because the page shipped with it before the iPad existed.
        "overlay": ROOT / "assets" / "img" / "device-frame.webp",
    },
    "ipad": {
        "frame": CACHE / "ipad-pro-13-m4-space-black.png",
        "url": BASE_URL + "iPadOS/iPad%20Pro/M4%20%26%20M5/13/"
                          "iPad%20Pro%2013%20M4%20%26%20M5%20-%20Portrait%20-%20Space%20Black.png",
        "aperture": (100, 100),
        "screen": (2064, 2752),
        "overlay": ROOT / "assets" / "img" / "device-frame-ipad.webp",
    },
}


def load_frame(device: dict) -> Image.Image:
    path = device["frame"]
    if not path.exists():
        CACHE.mkdir(parents=True, exist_ok=True)
        print(f"downloading device frame -> {path}")
        urllib.request.urlretrieve(device["url"], path)
    return Image.open(path).convert("RGBA")


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


def save_web(canvas: Image.Image, dest: Path) -> None:
    """One place that decides how a served image is encoded."""
    canvas.save(dest, format="WEBP", quality=QUALITY,
                alpha_quality=ALPHA_QUALITY, method=6)


def fit(canvas: Image.Image, max_w: int) -> Image.Image:
    if canvas.width <= max_w:
        return canvas
    h = round(canvas.height * max_w / canvas.width)
    return canvas.resize((max_w, h), Image.LANCZOS)


def frame_device(name: str, device: dict) -> int:
    frame = load_frame(device)
    mask = body_mask(frame)
    src = SRC / name
    out = src / "framed"
    out.mkdir(parents=True, exist_ok=True)

    overlay = fit(zero_transparent(frame), MAX_W["bezel"])
    save_web(overlay, device["overlay"])
    print(f"[{name}] bezel overlay {overlay.size} -> {device['overlay'].relative_to(ROOT)}")

    shots = sorted(p for p in src.glob("*.png") if p.is_file())
    if not shots:
        print(f"no screenshots in {src}", file=sys.stderr)
        return 1

    for shot in shots:
        screen = Image.open(shot).convert("RGBA")
        if screen.size != device["screen"]:
            print(f"  {shot.name}: {screen.size} -> resizing to {device['screen']}")
            screen = screen.resize(device["screen"], Image.LANCZOS)

        canvas = Image.new("RGBA", frame.size, (0, 0, 0, 0))
        canvas.paste(screen, device["aperture"])
        canvas.putalpha(ImageChops.multiply(canvas.getchannel("A"), mask))
        canvas.alpha_composite(frame)

        canvas = fit(zero_transparent(canvas), MAX_W["shot"])

        dest = (out / shot.name).with_suffix(".webp")
        save_web(canvas, dest)
        print(f"[{name}] framed {shot.name} {canvas.size} -> {dest.relative_to(ROOT)}")

    return 0


def main(argv: list[str]) -> int:
    wanted = argv[1:] or list(DEVICES)
    unknown = [d for d in wanted if d not in DEVICES]
    if unknown:
        print(f"unknown device(s): {', '.join(unknown)}", file=sys.stderr)
        print(f"known: {', '.join(DEVICES)}", file=sys.stderr)
        return 2
    return max(frame_device(name, DEVICES[name]) for name in wanted)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

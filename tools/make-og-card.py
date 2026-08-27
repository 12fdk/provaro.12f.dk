#!/usr/bin/env python3
"""Draw the Open Graph card.

`assets/og/og-image.png` was a committed PNG with nothing that rebuilt it, so
when the page gained an iPad and then a new palette the card stayed behind on
both, and a logo badge sat on top of the headline for months because no pass
ever regenerated it (#18). This is the generator that did not exist.

Three things it fixes by construction rather than by eye:

  * **Both devices.** The page has an iPhone and an iPad twin of every screen;
    the card is the image that actually travels, and it said iPhone only.
  * **Nothing overlaps the headline.** The old card's round mark covered the
    first characters of two lines, so it read "…eport your …stomer will share".
    The layout here keeps the mark in its own band and `assert_clear()` fails
    the build if the two boxes ever intersect again.
  * **The page's own palette and type.** Cement grey, navy and one red, set in
    Archivo and IBM Plex Mono — read straight out of `assets/fonts/`, converted
    in memory. No font CDN, and no chance of the card drifting onto a typeface
    the page does not use.

    python3 tools/make-og-card.py

Facebook, LinkedIn, Slack and X all cache aggressively, so a redraw does not
show up on a link that has already been shared. That is a property of their
caches, not of this file.
"""

from __future__ import annotations

import io
from pathlib import Path

from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "og" / "og-image.png"

# The card is the size every scraper crops to. Anything that must be read has
# to survive being shown at a third of this in a message list.
W, H = 1200, 630
PAD = 64

# css/styles.css, verbatim.
NAVY = (10, 29, 58)
PAPER = (255, 255, 255)
MARKUP = (226, 61, 46)
MUTED = (150, 165, 190)

FONTS = ROOT / "assets" / "fonts"
ARCHIVO = FONTS / "archivo-400_800-latin.woff2"
MONO = FONTS / "ibm-plex-mono-500-latin.woff2"

EYEBROW = "PHOTO REPORTS FOR TRADES"
HEADLINE = ["Photograph the job.", "Hand over the proof."]
FOOTER = "One payment  ·  No subscription  ·  Works offline"


def load(path: Path, size: int, weight: int | None = None,
         width: int | None = None) -> ImageFont.FreeTypeFont:
    """A woff2 from the page, as something Pillow can set type with.

    The site self-hosts its fonts so no CDN sees a visitor; converting in memory
    keeps that true of the card and guarantees it is the same typeface the page
    is set in rather than a lookalike.
    """
    face = TTFont(path)
    buf = io.BytesIO()
    face.flavor = None
    face.save(buf)
    buf.seek(0)
    font = ImageFont.truetype(buf, size)
    if weight is not None:
        # Archivo is variable, and the axes are (Weight, Width) in that order —
        # passing them the other way round sets weight 100 and clamps width,
        # which draws a headline thinner and wider than the page's rather than
        # failing. The order is asserted below so it cannot silently flip.
        axes = font.get_variation_axes()
        names = [a["name"].decode() if isinstance(a["name"], bytes) else a["name"]
                 for a in axes]
        assert names[:2] == ["Weight", "Width"], "Archivo axes moved: %s" % names
        font.set_variation_by_axes([weight, width if width is not None else 100])
    return font


def tracked(draw: ImageDraw.ImageDraw, xy, text, font, fill, tracking=0.0):
    """Letter-spaced text, which Pillow does not do and the eyebrow needs."""
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=font, fill=fill)
        x += draw.textlength(ch, font=font) + tracking
    return x - tracking


def assert_clear(a, b, what):
    """The bug this file exists to prevent: two boxes that must not overlap."""
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    if ax0 < bx1 and bx0 < ax1 and ay0 < by1 and by0 < ay1:
        raise SystemExit("og card: %s overlap — %s and %s" % (what, a, b))


def fit_lines(lines, column, start, floor=40):
    """The biggest size at which the headline still clears the devices.

    Sized rather than guessed, because the failure #18 is about is type running
    under a picture, and a hand-picked point size only holds until the copy
    changes.
    """
    for size in range(start, floor - 1, -2):
        font = load(ARCHIVO, size, weight=800, width=100)
        probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
        if max(probe.textlength(l, font=font) for l in lines) <= column:
            return font, size
    raise SystemExit("og card: headline will not fit %dpx even at %d" % (column, floor))


def device(path: Path, target_w: int) -> Image.Image:
    shot = Image.open(ROOT / path).convert("RGBA")
    h = round(shot.height * target_w / shot.width)
    return shot.resize((target_w, h), Image.LANCZOS)


def main() -> int:
    card = Image.new("RGB", (W, H), NAVY)
    draw = ImageDraw.Draw(card)

    # --- the devices, laid in first so the type sits over the bleed ----------
    # Both, because the page has both and the card is what travels. They run off
    # the bottom edge on purpose: a device cropped by the frame reads as a
    # photograph of a screen, a device floating clear of it reads as clip art.
    ipad = device(Path("assets/screens/ipad/framed/report-editor.webp"), 372)
    iphone = device(Path("assets/screens/iphone/framed/markup.webp"), 222)
    ipad_at, iphone_at = (664, 148), (958, 210)
    card.paste(ipad, ipad_at, ipad)
    card.paste(iphone, iphone_at, iphone)
    device_boxes = [
        (ipad_at[0], ipad_at[1], ipad_at[0] + ipad.width, ipad_at[1] + ipad.height),
        (iphone_at[0], iphone_at[1], iphone_at[0] + iphone.width,
         iphone_at[1] + iphone.height),
    ]

    # --- the mark, in its own band ------------------------------------------
    logo = Image.open(ROOT / "assets" / "img" / "logo.png").convert("RGBA")
    logo = logo.resize((52, 52), Image.LANCZOS)
    logo_box = (PAD, PAD, PAD + 52, PAD + 52)
    card.paste(logo, (PAD, PAD), logo)

    wordmark = load(ARCHIVO, 34, weight=700, width=112)
    draw.text((PAD + 68, PAD + 6), "Provaro", font=wordmark, fill=PAPER)

    # --- eyebrow, headline, footer ------------------------------------------
    mono = load(MONO, 17)
    tracked(draw, (PAD, 214), EYEBROW, mono, MUTED, tracking=2.6)

    column = min(b[0] for b in device_boxes) - PAD - 28
    head, size = fit_lines(HEADLINE, column, start=58)
    lead = round(size * 1.18)
    y = 252
    head_top = y
    widest = 0
    for line in HEADLINE:
        draw.text((PAD, y), line, font=head, fill=PAPER)
        widest = max(widest, draw.textlength(line, font=head))
        y += lead
    head_box = (PAD, head_top, PAD + round(widest), y)

    # The whole point of the rewrite: nothing sits on the words again — not the
    # mark, which is what shipped, and not the devices, which is what the first
    # draft of this generator did.
    assert_clear(logo_box, head_box, "logo and headline")
    for i, box in enumerate(device_boxes):
        assert_clear(box, head_box, "device %d and headline" % (i + 1))

    # One red, used the way the page uses it: as a mark, never as type.
    draw.rectangle((PAD, y + 26, PAD + 64, y + 30), fill=MARKUP)

    foot = load(MONO, 17)
    tracked(draw, (PAD, y + 58), FOOTER, foot, MUTED, tracking=0.6)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    card.save(OUT, optimize=True)
    print("%s  %dx%d  %.0f KB" % (OUT.relative_to(ROOT), W, H,
                                  OUT.stat().st_size / 1024))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

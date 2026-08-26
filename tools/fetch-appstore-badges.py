#!/usr/bin/env python3
"""Fetch Apple's official App Store badge, in each language the site is in.

Same argument as tools/fetch-appstore-price.py: nobody should be hand-carrying
Apple's assets into this repo. Apple publishes the badge per storefront
language and serves it as SVG, so ask for it rather than draw it:

    https://toolbox.marketingtools.apple.com/api/badges/
        download-on-the-app-store/black/<locale>?size=250x83

The English file this repo already had is byte-for-byte what that endpoint
returns for en-us, which is the check that this is the same artwork the badge
has always been, in more languages.

The badges are not all the same shape — French is wider, Japanese is narrower —
and `.appstore img` is sized in CSS, so the width/height attributes on the <img>
exist only to reserve the right space before the SVG arrives. tools/build-i18n.py
reads the intrinsic size back out of these files rather than assuming 120.

Run with --check to fail instead of writing, which is what CI wants when it is
only asking "has Apple redrawn anything?".
"""

import argparse
import pathlib
import re
import sys
import time
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
IMG = ROOT / "assets" / "img"

ENDPOINT = ("https://toolbox.marketingtools.apple.com/api/badges/"
            "download-on-the-app-store/black/%s?size=250x83")

# Site language -> the storefront locale whose badge it should carry. English
# keeps the unsuffixed filename, because index.html is written by hand and
# should not have to know about this table.
BADGES = {
    None: "en-us",
    "de": "de-de",
    "es": "es-es",
    "fr": "fr-fr",
    "it": "it-it",
    "ja": "ja-jp",
    "nl": "nl-nl",
    "pl": "pl-pl",
    "pt-br": "pt-br",
}

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15")


def path_for(lang):
    return IMG / ("appstore-badge.svg" if lang is None
                  else "appstore-badge-%s.svg" % lang)


def fetch(url, attempts=4):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code not in (429,) and not 500 <= e.code < 600:
                raise
            if attempt == attempts - 1:
                raise
            time.sleep(int(e.headers.get("Retry-After") or 0) or 3 * (attempt + 1))
        except urllib.error.URLError:
            if attempt == attempts - 1:
                raise
            time.sleep(3 * (attempt + 1))


def measure(svg):
    """The badge's intrinsic size, which is not the same in every language."""
    width = re.search(r'\bwidth="([\d.]+)"', svg)
    height = re.search(r'\bheight="([\d.]+)"', svg)
    if not width or not height:
        raise ValueError("no width/height on the root <svg>")
    return float(width.group(1)), float(height.group(1))


def verify(svg, locale):
    """Refuse to write anything that is not Apple's badge.

    An endpoint that starts answering with an error page, a redirect notice or
    somebody else's artwork must not end up on the page under an alt text
    promising the App Store.
    """
    if not svg.lstrip().startswith("<svg"):
        raise ValueError("not an SVG document")
    title = re.search(r"<title>([^<]*)</title>", svg)
    if not title or not title.group(1).startswith("Download_on_the_App_Store_Badge"):
        raise ValueError("title is %r, not Apple's badge"
                         % (title.group(1) if title else None))
    measure(svg)
    return title.group(1)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="report differences without writing")
    args = ap.parse_args()

    changed, failed = [], []
    for lang, locale in BADGES.items():
        label = lang or "en"
        try:
            svg = fetch(ENDPOINT % locale)
            title = verify(svg, locale)
        except Exception as e:
            print("  %-6s FAILED: %s" % (label, e), file=sys.stderr)
            failed.append(label)
            continue

        width, height = measure(svg)
        dest = path_for(lang)
        before = dest.read_text(encoding="utf-8") if dest.exists() else None
        mark = "unchanged"
        if before != svg:
            mark = "NEW" if before is None else "CHANGED"
            changed.append(label)
            if not args.check:
                dest.write_text(svg, encoding="utf-8")
        print("  %-6s %-9s %7.2f x %.0f  %s" % (label, mark, width, height, title))

    if failed:
        raise SystemExit("could not fetch: %s" % ", ".join(failed))
    if not changed:
        print("Apple has not redrawn anything.")
        return 0
    if args.check:
        raise SystemExit("would rewrite: %s" % ", ".join(changed))
    print("Wrote %d badge(s). Run tools/build-i18n.py so the pages pick up "
          "any change in size." % len(changed))
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Read Provaro's prices off the App Store and write them into the page.

Nobody should be typing a price into index.html. Apple is the only party that
knows what a customer is actually charged, and the number moves without asking
us — a tier repricing, a VAT change, a new storefront. This script asks Apple
and writes the answer into the two places the page keeps a price: the marked
spans in index.html (what a visitor reads, and what a crawler reads with no
JavaScript) and assets/data/pricing.json (what the inline script uses to show
a visitor their own storefront's number).

Two sources, because Apple splits the answer in two:

  * The app itself is free, and the public iTunes lookup API says so.
  * "Pro (Lifetime)" is an in-app purchase, and lookup does not report those.
    The App Store product page does: it embeds the annotation rows as
    {"$kind":"textPair","leadingText":"Pro (Lifetime)","trailingText":"9,99 €"}.
    That JSON carries the price already formatted for the storefront, which is
    exactly what we want to print, and it is language-agnostic — the German
    page labels the section "In-App-Käufe" but the pair looks the same.

Run with --check to fail instead of writing, which is what CI wants when it is
only asking "has Apple moved?".
"""

import argparse
import hashlib
import json
import pathlib
import re
import sys
import time
import urllib.error
import urllib.request

APP_ID = "6800068309"
IAP_NAME = "Pro (Lifetime)"

ROOT = pathlib.Path(__file__).resolve().parent.parent
INDEX = ROOT / "index.html"
PRICING = ROOT / "assets" / "data" / "pricing.json"

# Storefronts we publish. `primary` is the one baked into the HTML for everyone
# who does not match a storefront below; `secondary` is the number the Pro card
# quotes alongside it, for the home market.
PRIMARY = "ie"     # euro, formatted the way an English page reads it
SECONDARY = "dk"   # kroner, quoted next to it on the Pro card

# Storefront -> the regions whose visitors are charged that storefront's price.
# Region codes are what Intl/navigator.language hand us; the inline script does
# the matching, this table only decides what we go and fetch.
STOREFRONTS = {
    # One euro tier covers the whole eurozone; Ireland is the storefront that
    # prints it in English, which is the language this page is written in.
    "ie": ["IE", "AT", "BE", "CY", "DE", "EE", "ES", "FI", "FR", "GR", "HR",
           "IT", "LT", "LU", "LV", "MT", "NL", "PT", "SI", "SK"],
    "dk": ["DK"],
    "se": ["SE"],
    "no": ["NO"],
    "gb": ["GB"],
    "us": ["US"],
    "ca": ["CA"],
    "au": ["AU"],
    "nz": ["NZ"],
    "ch": ["CH"],
    "pl": ["PL"],
    "cz": ["CZ"],
}

# Safari's UA. Apple serves the product page to anything, but a plausible
# browser is the version that keeps getting the embedded annotation JSON.
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15")


def fetch(url, attempts=4):
    """GET, with a pause for Apple's rate limiter.

    A shared runner IP asks for a dozen storefronts in a row and Apple answers
    one of them with a 429. Backing off and asking again is enough; giving up
    on that storefront is not, because the price would silently vanish from
    the page for everyone it covers.
    """
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            retriable = e.code == 429 or 500 <= e.code < 600
            if not retriable or attempt == attempts - 1:
                raise
            wait = int(e.headers.get("Retry-After") or 0) or 3 * (attempt + 1)
            print(f"    {e.code} — waiting {wait}s", file=sys.stderr)
            time.sleep(wait)
        except urllib.error.URLError:
            if attempt == attempts - 1:
                raise
            time.sleep(3 * (attempt + 1))


def app_price(storefront):
    """The price of the app download itself, from the public lookup API."""
    data = json.loads(fetch(
        f"https://itunes.apple.com/lookup?id={APP_ID}&country={storefront}"))
    if not data.get("resultCount"):
        raise LookupError(f"lookup returned nothing for {storefront!r}")
    r = data["results"][0]
    return {"amount": r["price"], "formatted": r["formattedPrice"],
            "currency": r["currency"]}


def iap_price(storefront):
    """The formatted price of the Pro in-app purchase, off the product page."""
    page = fetch(f"https://apps.apple.com/{storefront}/app/id{APP_ID}")

    # The embedded annotation JSON, which every storefront language shares.
    pair = re.search(
        r'"leadingText":"%s","trailingText":"((?:[^"\\]|\\.)*)"'
        % re.escape(IAP_NAME), page)
    if pair:
        return json.loads('"%s"' % pair.group(1))

    # Fall back to the rendered row, in case Apple stops shipping the JSON.
    row = re.search(
        r'<span>%s</span>\s*<span>([^<]+)</span>' % re.escape(IAP_NAME), page)
    if row:
        return row.group(1)

    raise LookupError(f"no {IAP_NAME!r} price on the {storefront} page")


def numeric(formatted):
    """9,99 € -> 9.99, 99,00 kr -> 99.0, $9.99 -> 9.99. For schema.org."""
    m = re.search(r"\d[\d.,   ]*\d|\d", formatted)
    if not m:
        raise ValueError(f"no number in {formatted!r}")
    n = re.sub(r"[   ]", "", m.group(0))
    # Whichever separator comes last is the decimal one; the other groups.
    if "," in n and "." in n:
        dec = "," if n.rindex(",") > n.rindex(".") else "."
        n = n.replace("." if dec == "," else ",", "").replace(dec, ".")
    elif "," in n:
        # A lone comma is decimal (9,99) unless it is grouping (1,299).
        n = n.replace(",", "." if len(n.split(",")[-1]) != 3 else "")
    return float(n)


def zero_like(formatted):
    """"€9.99" -> "€0", "99,00 kr" -> "0 kr". The free tier, in the storefront's
    own currency, without borrowing the storefront's language: the lookup API
    would hand us "Gratis" on the German page, which is not English."""
    return re.sub(r"\d[\d.,   ]*\d|\d", "0", formatted, count=1)


def collect(previous):
    """Everything Apple will tell us, for every storefront we publish."""
    out = {}
    for i, sf in enumerate(STOREFRONTS):
        if i:
            time.sleep(1)  # a dozen requests in a row is what trips the 429
        try:
            free, pro = app_price(sf), iap_price(sf)
        except (urllib.error.URLError, LookupError, ValueError, KeyError) as e:
            # One unreachable storefront must not cost us its price. Keep what
            # Apple told us last time rather than dropping the storefront and
            # quoting those visitors a currency they are not billed in.
            if sf in previous:
                out[sf] = previous[sf]
                print(f"  {sf}: unreachable ({e}) — keeping {previous[sf]['pro']}",
                      file=sys.stderr)
            else:
                print(f"  {sf}: unreachable ({e}) — no previous price to keep",
                      file=sys.stderr)
            continue
        # The app download is free everywhere today, and "0 €" beside the Pro
        # price reads better than the word — but if a storefront ever charges
        # for the download, print what Apple says it charges.
        shown = free["formatted"] if free["amount"] else zero_like(pro)
        out[sf] = {
            "regions": STOREFRONTS[sf],
            "currency": free["currency"],
            "free": shown,
            "pro": pro,
            "proAmount": numeric(pro),
        }
        print(f"  {sf}: free {shown}, pro {pro}")
    return out


def nbsp(price):
    """Keep the number and its currency on one line, the way the page does."""
    return re.sub(r"[   ]", "&nbsp;", price.strip())


def rewrite(html, prices, version):
    """Put the fetched numbers into every marked price in the page.

    Each price in index.html is wrapped in <span data-price="free|pro">, and
    the JSON-LD offers carry the same amounts. Both are replaced here, so the
    page is right before a single line of JavaScript runs.
    """
    primary, secondary = prices[PRIMARY], prices[SECONDARY]

    subs = {
        "free": nbsp(primary["free"]),
        "pro": nbsp(primary["pro"]),
        "pro-secondary": nbsp(secondary["pro"]),
    }

    def span(m):
        key = m.group(2)
        if key not in subs:
            raise KeyError(f'unknown data-price="{key}" in index.html')
        return f'{m.group("open")}{subs[key]}</span>'

    html, n = re.subn(
        r'(?P<open><span[^>]*\bdata-price="([a-z-]+)"[^>]*>).*?</span>',
        span, html)
    if n == 0:
        raise SystemExit("index.html has no data-price spans to fill in")
    print(f"  rewrote {n} price spans")

    # schema.org wants a bare amount and an ISO currency, not a formatted one.
    amount = f'{primary["proAmount"]:g}'
    html = re.sub(r'("@type": "Offer", "price": ")[^"]*(", "priceCurrency": ")'
                  r'[^"]*(", "description": "Pro)',
                  rf'\g<1>{amount}\g<2>{primary["currency"]}\g<3>', html)
    html = re.sub(r'("@type": "Offer", "price": ")[^"]*(", "priceCurrency": ")'
                  r'[^"]*(", "description": "Free)',
                  rf'\g<1>0\g<2>{primary["currency"]}\g<3>', html)

    # The FAQ answer in JSON-LD spells the price out in prose, so it needs the
    # amount and the currency code the way a person would say them.
    spoken = f'{amount} {primary["currency"]}'
    html = re.sub(r"(Pro is a single )[^ ]+ [A-Z]{3}( payment)",
                  rf"\g<1>{spoken}\g<2>", html)

    # Pages serves pricing.json without a hash in its name, so the inline
    # script would keep reading a cached copy after a price change. The token
    # is the payload's own digest: it moves only when the prices move.
    html = re.sub(r"(assets/data/pricing\.json\?v=)[^']*",
                  rf"\g<1>{version}", html)

    return html


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="fail if the page is out of date, write nothing")
    args = ap.parse_args()

    print("Asking Apple:")
    previous = {}
    if PRICING.exists():
        previous = json.loads(PRICING.read_text(encoding="utf-8")).get(
            "storefronts", {})
    prices = collect(previous)

    # Storefronts are ordered as declared, so a kept price does not reshuffle
    # the file and show up as a diff.
    prices = {sf: prices[sf] for sf in STOREFRONTS if sf in prices}
    for sf in (PRIMARY, SECONDARY):
        if sf not in prices:
            raise SystemExit(
                f"the {sf} storefront is what the page is built from and it "
                f"could not be read — refusing to write a half-answer")

    payload = json.dumps({"appId": APP_ID, "product": IAP_NAME,
                          "primary": PRIMARY, "secondary": SECONDARY,
                          "storefronts": prices},
                         ensure_ascii=False, indent=2) + "\n"
    version = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:8]

    before = INDEX.read_text(encoding="utf-8")
    after = rewrite(before, prices, version)
    was = PRICING.read_text(encoding="utf-8") if PRICING.exists() else ""

    stale = after != before or payload != was
    if args.check:
        print("out of date" if stale else "up to date")
        return 1 if stale else 0

    if after != before:
        INDEX.write_text(after, encoding="utf-8")
        print(f"  wrote {INDEX.relative_to(ROOT)}")
    if payload != was:
        PRICING.parent.mkdir(parents=True, exist_ok=True)
        PRICING.write_text(payload, encoding="utf-8")
        print(f"  wrote {PRICING.relative_to(ROOT)}")
    if not stale:
        print("  nothing changed")
    return 0


if __name__ == "__main__":
    sys.exit(main())

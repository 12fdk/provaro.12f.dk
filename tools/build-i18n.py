#!/usr/bin/env python3
"""Generate the translated landing pages from index.html and i18n/*.json.

index.html is the only page anybody writes by hand. This reads it, pulls out
every translatable unit — the inner HTML of each leaf block, the handful of
attributes a reader can see, and the string fields of the two JSON-LD blocks —
and splices a language's catalogue back in to produce `<lang>/index.html`.

Eight copies of a nine-hundred-line file cannot be kept in step by hand: the
first English edit leaves seven pages quietly wrong. Generating them turns that
into an error message. `--check` fails when a catalogue has drifted from the
English source, so a copy change surfaces in CI rather than on the page.

    tools/build-i18n.py --extract     rewrite i18n/en.json from index.html
    tools/build-i18n.py               write every <lang>/index.html
    tools/build-i18n.py --check       fail if a catalogue is stale, write nothing

Two things are deliberately kept out of the catalogues:

  * Prices. The content of every <span data-price> is blanked before a unit
    becomes a msgid, so Apple moving a price never invalidates a translation.
    Each page is then filled from assets/data/pricing.json with the storefront
    its readers actually buy from — /de/ prints euros the German way, /ja/
    prints yen — and the JSON-LD offer is restated in that currency.
  * Language names. The switcher lists every translation in its own language,
    which is the same list on every page, so it is built here rather than
    translated nine times.

The App Store badge is artwork, not copy, so it is not in the catalogues
either: each page is pointed at Apple's own badge for its language, at whatever
size that badge happens to be. tools/fetch-appstore-badges.py fetches them.
"""

import argparse
import json
import pathlib
import re
import sys
from html.parser import HTMLParser

ROOT = pathlib.Path(__file__).resolve().parent.parent
INDEX = ROOT / "index.html"
I18N = ROOT / "i18n"
PRICING = ROOT / "assets" / "data" / "pricing.json"
SITE = "https://provaro.12f.dk/"


# --- The languages -----------------------------------------------------------
# `store` is the App Store storefront the download links point at; `primary` and
# `second` are keys in pricing.json — `second` is the familiar currency quoted
# beside the price in the small print, and None where there isn't one worth
# quoting. Swiss francs earn the aside on the German, French and Italian pages
# for the same reason kroner earn it on the English one: a lot of the readers
# are billed in it.
LANGUAGES = {
    "de": dict(dirname="de", tag="de", locale="de_DE", code="DE", name="Deutsch",
               aria="Sprache", store="de", primary="de", second="ch"),
    "es": dict(dirname="es", tag="es", locale="es_ES", code="ES", name="Español",
               aria="Idioma", store="es", primary="es", second=None),
    "fr": dict(dirname="fr", tag="fr", locale="fr_FR", code="FR", name="Français",
               aria="Langue", store="fr", primary="fr", second="ch"),
    "it": dict(dirname="it", tag="it", locale="it_IT", code="IT", name="Italiano",
               aria="Lingua", store="it", primary="it", second="ch"),
    "ja": dict(dirname="ja", tag="ja", locale="ja_JP", code="JA", name="日本語",
               aria="言語", store="jp", primary="jp", second=None),
    "nl": dict(dirname="nl", tag="nl", locale="nl_NL", code="NL", name="Nederlands",
               aria="Taal", store="nl", primary="nl", second=None),
    "pl": dict(dirname="pl", tag="pl", locale="pl_PL", code="PL", name="Polski",
               aria="Język", store="pl", primary="pl", second=None),
    "pt-br": dict(dirname="pt-br", tag="pt-BR", locale="pt_BR", code="PT",
                  name="Português (BR)", aria="Idioma", store="br",
                  primary="br", second=None),
}

# The English page is one of the nine the switcher lists, and it is the
# x-default, so it belongs in the same table when the menu is built.
ENGLISH = dict(dirname="", tag="en", locale="en_GB", code="EN", name="English",
               aria="Language", store="us", primary="ie", second="dk")


# --- What counts as a translatable unit --------------------------------------
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
        "meta", "param", "source", "track", "wbr"}

# A block element ends the unit its parent would otherwise have been: a <div>
# holding three <p>s is not one string, it is three.
BLOCK = {"html", "head", "body", "header", "footer", "main", "section",
         "article", "aside", "nav", "div", "ul", "ol", "li", "dl", "dt", "dd",
         "details", "summary", "figure", "figcaption", "form", "fieldset",
         "legend", "table", "thead", "tbody", "tr", "td", "th", "video",
         "picture", "audio", "p", "h1", "h2", "h3", "h4", "h5", "h6",
         "blockquote", "pre", "title", "label", "script", "style", "noscript",
         "iframe", "canvas", "select", "option", "textarea", "button", "svg"}

# Anything a sentence can run through stays inside the unit — <a>, <strong>,
# the price span — so a translator can move it to where their grammar wants it.
CANDIDATE = {"title", "h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "summary",
             "figcaption", "legend", "label", "a", "span", "strong", "b",
             "small", "div", "td", "th", "dd", "dt", "blockquote"}

ATTRS = ("alt", "title", "aria-label", "data-value", "placeholder")

META_CONTENT = {
    ("name", "description"),
    ("property", "og:title"),
    ("property", "og:description"),
    ("name", "twitter:title"),
    ("name", "twitter:description"),
}

# "9.99 EUR" inside a JSON-LD answer would tie every catalogue to today's price.
PRICE_IN_PROSE = re.compile(r"\d+(?:[.,]\d{2})?\s+[A-Z]{3}\b")


class Node:
    __slots__ = ("tag", "attrs", "raw", "open_end", "close_start", "children",
                 "void")

    def __init__(self, tag, attrs, raw, open_end, void=False):
        self.tag = tag
        self.attrs = attrs
        self.raw = raw                  # offset of '<'
        self.open_end = open_end        # offset just after the start tag
        self.close_start = open_end     # offset of '</'
        self.children = []
        self.void = void                # nothing to close: <img />, a comment

    def attr(self, name):
        return self.attrs.get(name)


class Tree(HTMLParser):
    """A parse tree that remembers where in the source every element sits."""

    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.text = text
        self.starts = [0]
        for line in text.split("\n"):
            self.starts.append(self.starts[-1] + len(line) + 1)
        self.root = Node("#document", {}, 0, 0)
        self.root.close_start = len(text)
        self.stack = [self.root]
        self.feed(text)

    def _at(self):
        line, col = self.getpos()
        return self.starts[line - 1] + col

    def _open(self, tag, attrs, void):
        pos = self._at()
        node = Node(tag, {k: (v or "") for k, v in attrs}, pos,
                    pos + len(self.get_starttag_text()), void)
        self.stack[-1].children.append(node)
        return node

    def handle_starttag(self, tag, attrs):
        node = self._open(tag, attrs, tag in VOID)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self._open(tag, attrs, True)

    def _marker(self, tag, length):
        """A comment or a doctype: not content, but it fills a gap that would
        otherwise be read as loose text."""
        pos = self._at()
        self.stack[-1].children.append(Node(tag, {}, pos, pos + length, True))

    def handle_comment(self, data):
        self._marker("#comment", len(data) + 7)

    def handle_decl(self, decl):
        self._marker("#decl", len(decl) + 3)

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        for depth in range(len(self.stack) - 1, 0, -1):
            if self.stack[depth].tag == tag:
                pos = self._at()
                node = self.stack[depth]
                node.close_start = pos
                del self.stack[depth:]
                return


def norm(s):
    """A msgid is one line: the English source can be rewrapped without
    invalidating eight catalogues."""
    return re.sub(r"\s+", " ", s).strip()


def blank_prices(s):
    return re.sub(r'(<span data-price="[^"]+"[^>]*>).*?(</span>)', r"\1\2", s,
                  flags=re.S)


def opaque(node):
    """Subtrees this tool must not look inside, let alone rewrite. Anything
    aria-hidden is decoration — the step numbers, the device bezels — and a
    decoration is not copy."""
    return (node.tag in ("svg", "script", "style")
            or node.attr("translate") == "no"
            or node.attr("aria-hidden") == "true")


def blocks_parent(node):
    """Does this child stop its parent from being a single string?"""
    return node.tag in BLOCK or opaque(node) or any(
        a in node.attrs for a in ATTRS)


def has_block(node):
    for child in node.children:
        if blocks_parent(child) or has_block(child):
            return True
    return False


def inner(text, node):
    return text[node.open_end:node.close_start]


def child_end(text, child):
    """Offset just past a child element, closing tag included."""
    if child.void:
        return child.open_end
    return text.index(">", child.close_start) + 1


class Extraction:
    """Every translatable region of index.html, keyed by its English text."""

    def __init__(self, text):
        self.text = text
        self.order = []                 # msgids, in document order
        self.seen = set()
        self.edits = []                 # (start, end, kind, payload)
        self.ld = []                    # (start, end, parsed json, [(path, msgid)])
        tree = Tree(text)
        self._walk(tree.root, inside_unit=False)
        self.edits.sort(key=lambda e: e[0])

    def _msgid(self, raw):
        msgid = blank_prices(norm(raw))
        if msgid and msgid not in self.seen:
            self.seen.add(msgid)
            self.order.append(msgid)
        return msgid

    def _attributes(self, node):
        raw = self.text[node.raw:node.open_end]
        for match in re.finditer(r'([a-zA-Z-]+)\s*=\s*"([^"]*)"', raw):
            name, value = match.group(1).lower(), match.group(2)
            if not value.strip():
                continue
            if name == "content":
                if not any(node.attr(k) == v for k, v in META_CONTENT):
                    continue
            elif name not in ATTRS:
                continue
            start = node.raw + match.start(2)
            self.edits.append((start, node.raw + match.end(2), "attr",
                               self._msgid(value)))

    def _walk(self, node, inside_unit):
        if node.tag in ("#comment", "#decl"):
            return
        if opaque(node) and node.tag != "script":
            return
        if node.tag == "script":
            if node.attr("type") == "application/ld+json":
                self._jsonld(node)
            return

        if not inside_unit:
            self._attributes(node)

        if not inside_unit and node.tag in CANDIDATE and not has_block(node):
            body = inner(self.text, node)
            if body.strip() and re.sub(r"<[^>]*>", "", body).strip():
                self.edits.append((node.open_end, node.close_start, "unit",
                                   self._msgid(body)))
                return

        # Text sitting loose inside a container — the <video> fallback line.
        pos = node.open_end
        for child in node.children:
            if child.raw > pos and not inside_unit:
                self._loose(pos, child.raw)
            pos = child_end(self.text, child)
            self._walk(child, inside_unit)
        if node.close_start > pos and not inside_unit:
            self._loose(pos, node.close_start)

    def _loose(self, start, end):
        chunk = self.text[start:end]
        if not chunk.strip():
            return
        lead = len(chunk) - len(chunk.lstrip())
        trail = len(chunk) - len(chunk.rstrip())
        self.edits.append((start + lead, end - trail, "unit",
                           self._msgid(chunk)))

    def _jsonld(self, node):
        data = json.loads(inner(self.text, node))
        strings = []
        for path, value in ld_strings(data):
            strings.append((path, self._msgid(PRICE_IN_PROSE.sub("{pro}", value))))
        self.ld.append((node.open_end, node.close_start, data, strings))
        self.edits.append((node.open_end, node.close_start, "ld",
                           len(self.ld) - 1))


def ld_strings(obj, path=(), parent=None):
    """The string fields of a schema.org block that are prose, not data."""
    if isinstance(obj, dict):
        for key, value in obj.items():
            if isinstance(value, str):
                if key in ("description", "text") or (
                        key == "name" and obj.get("@type") == "Question"):
                    yield path + (key,), value
            else:
                yield from ld_strings(value, path + (key,), obj)
    elif isinstance(obj, list):
        for i, value in enumerate(obj):
            if isinstance(value, str):
                if path and path[-1] == "featureList":
                    yield path + (i,), value
            else:
                yield from ld_strings(value, path + (i,), parent)


def ld_set(obj, path, value):
    for step in path[:-1]:
        obj = obj[step]
    obj[path[-1]] = value


# --- Generating a page -------------------------------------------------------
def alternates_block(text):
    match = re.search(r"  <!-- i18n:alternates.*?<!-- /i18n:alternates -->",
                      text, re.S)
    if not match:
        raise SystemExit("index.html has no i18n:alternates block")
    return match.group(0)


def badge(doc, lang):
    """Point the page at Apple's badge in its own language.

    The badges are not all one shape — French runs wider than English, Japanese
    narrower — and .appstore img is sized in CSS, so the width and height on the
    <img> exist only to hold the right space open until the SVG lands. Read the
    size out of the file rather than trusting the number index.html happens to
    carry. tools/fetch-appstore-badges.py is what puts these files here.
    """
    name = "appstore-badge-%s.svg" % lang["dirname"]
    art = ROOT / "assets" / "img" / name
    if not art.exists():
        raise SystemExit("no %s — run tools/fetch-appstore-badges.py" % name)
    svg = art.read_text(encoding="utf-8")
    size = re.search(r'<svg[^>]*\bwidth="([\d.]+)"[^>]*\bheight="([\d.]+)"', svg)
    if not size:
        raise SystemExit("%s has no intrinsic size" % name)
    width, height = float(size.group(1)), float(size.group(2))

    doc, n = re.subn(
        r'<img src="assets/img/appstore-badge\.svg"([^>]*?)'
        r'width="[\d.]+" height="([\d.]+)"',
        lambda m: '<img src="assets/img/%s"%swidth="%d" height="%s"' % (
            name, m.group(1), round(width * float(m.group(2)) / height), m.group(2)),
        doc)
    if not n:
        raise SystemExit("index.html has no App Store badge to localise")
    return doc


def langpick(current):
    order = [ENGLISH] + [LANGUAGES[k] for k in
                         ("de", "es", "fr", "it", "ja", "nl", "pl", "pt-br")]
    links = "\n".join(
        '          <a href="/%s" hreflang="%s" lang="%s"%s>%s</a>' % (
            (lang["dirname"] + "/") if lang["dirname"] else "",
            lang["tag"], lang["tag"],
            ' aria-current="true"' if lang is current else "", lang["name"])
        for lang in order)
    return (
        '      <details class="lang-pick" translate="no">\n'
        '        <summary aria-label="%s"><span class="lang-face">%s'
        '<svg width="10" height="10" viewBox="0 0 24 24" aria-hidden="true">'
        '<path d="M6 9l6 6 6-6" fill="none" stroke="currentColor" '
        'stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>'
        '</svg></span></summary>\n'
        '        <nav class="lang-menu" aria-label="%s">\n%s\n'
        '        </nav>\n'
        '      </details>' % (current["aria"], current["code"], current["aria"], links))


def render(extraction, catalogue, lang, prices):
    text = extraction.text
    store = prices["storefronts"][lang["primary"]]
    missing = []
    out = []
    pos = 0
    for start, end, kind, payload in extraction.edits:
        out.append(text[pos:start])
        if kind == "ld":
            _, _, data, strings = extraction.ld[payload]
            data = json.loads(json.dumps(data))
            for path, msgid in strings:
                ld_set(data, path, translate(catalogue, msgid, missing)
                       .replace("{pro}", store["pro"]))
            localise_ld(data, lang, store)
            body = json.dumps(data, ensure_ascii=False, indent=2)
            out.append("\n" + "\n".join("  " + line for line in body.split("\n"))
                       + "\n  ")
        else:
            out.append(translate(catalogue, payload, missing))
        pos = end
    out.append(text[pos:])
    doc = "".join(out)

    doc = doc.replace(
        '<html lang="en" data-price-primary="ie" data-price-secondary="dk">',
        '<html lang="%s" data-price-primary="%s" data-price-secondary="%s">' % (
            lang["tag"], lang["primary"], lang["second"] or "none"))
    doc = doc.replace('<link rel="canonical" href="%s" />' % SITE,
                      '<link rel="canonical" href="%s%s/" />' % (SITE, lang["dirname"]))
    doc = doc.replace('<meta property="og:url" content="%s" />' % SITE,
                      '<meta property="og:url" content="%s%s/" />' % (SITE, lang["dirname"]))
    doc = doc.replace('<meta property="og:locale" content="en_GB" />',
                      '<meta property="og:locale" content="%s" />' % lang["locale"])
    doc = re.sub(r"      <details class=\"lang-pick\".*?</details>",
                 lambda m: langpick(lang), doc, count=1, flags=re.S)
    doc = doc.replace("apps.apple.com/us/app/", "apps.apple.com/%s/app/" % lang["store"])
    doc = badge(doc, lang)

    # Prices: fill what the msgid blanked, then drop the second-currency aside
    # on a page that quotes only one.
    doc = re.sub(r'(<span data-price="([^"]+)"[^>]*>).*?(</span>)',
                 lambda m: m.group(1) + price_for(m.group(2), lang, prices) + m.group(3),
                 doc, flags=re.S)
    if not lang["second"]:
        doc = re.sub(r"<span data-price-aside>.*?</span>\s*</span>", "", doc, flags=re.S)

    # The page now lives one directory down.
    doc = re.sub(r'\b(src|href|poster)="(?!https?://|//|/|#|mailto:|tel:|data:)',
                 r'\1="../', doc)
    doc = doc.replace("'assets/data/pricing.json", "'../assets/data/pricing.json")
    return doc, missing


def price_for(key, lang, prices):
    sf = prices["storefronts"]
    if key == "pro-secondary":
        return sf[lang["second"]]["pro"] if lang["second"] else ""
    return sf[lang["primary"]][key]


def localise_ld(data, lang, store):
    if data.get("@type") == "MobileApplication":
        data["url"] = SITE + lang["dirname"] + "/"
        data["inLanguage"] = lang["tag"]
        data["installUrl"] = data["installUrl"].replace(
            "apps.apple.com/us/app/", "apps.apple.com/%s/app/" % lang["store"])
        for offer in data.get("offers", []):
            free = offer["price"] in ("0", "0.00", 0)
            offer["price"] = "0" if free else ("%g" % store["proAmount"])
            offer["priceCurrency"] = store["currency"]
    elif data.get("@type") == "FAQPage":
        data["inLanguage"] = lang["tag"]


def translate(catalogue, msgid, missing):
    if not msgid:
        return msgid
    value = catalogue.get(msgid)
    if not value:
        missing.append(msgid)
        return msgid
    return value


# --- Entry points ------------------------------------------------------------
def load(code):
    path = I18N / ("%s.json" % code)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8")).get("units", {})


def write_english(extraction):
    payload = {
        "@meta": {
            "language": "English",
            "note": "Generated by tools/build-i18n.py --extract. The source of "
                    "truth is index.html; this file is the list of units every "
                    "other catalogue must answer, in document order.",
        },
        "units": {msgid: msgid for msgid in extraction.order},
    }
    (I18N / "en.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--extract", action="store_true",
                    help="rewrite i18n/en.json from index.html and stop")
    ap.add_argument("--check", action="store_true",
                    help="report stale catalogues without writing any page")
    ap.add_argument("--only", metavar="LANG", help="build one language")
    args = ap.parse_args()

    text = INDEX.read_text(encoding="utf-8")
    extraction = Extraction(text)
    I18N.mkdir(exist_ok=True)

    if args.extract:
        write_english(extraction)
        print("i18n/en.json: %d units" % len(extraction.order))
        return 0

    prices = json.loads(PRICING.read_text(encoding="utf-8"))
    wanted = [args.only] if args.only else list(LANGUAGES)
    problems = 0
    for code in wanted:
        lang = LANGUAGES[code]
        catalogue = load(code)
        if catalogue is None:
            print("%-6s no catalogue (i18n/%s.json)" % (code, code))
            problems += 1
            continue
        doc, missing = render(extraction, catalogue, lang, prices)
        stale = [m for m in catalogue if m not in extraction.seen]
        note = ""
        if missing:
            note += "  %d untranslated" % len(set(missing))
        if stale:
            note += "  %d obsolete" % len(stale)
        print("%-6s %d units%s" % (code, len(extraction.order), note or "  complete"))
        for msgid in sorted(set(missing))[:8]:
            print("         missing: %s" % msgid[:96])
        if missing:
            problems += 1
        if not args.check:
            out = ROOT / lang["dirname"]
            out.mkdir(exist_ok=True)
            (out / "index.html").write_text(doc, encoding="utf-8")
    return 1 if (args.check and problems) else 0


if __name__ == "__main__":
    sys.exit(main())

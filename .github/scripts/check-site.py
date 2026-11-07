#!/usr/bin/env python3
"""Checks the site's files as committed, with no build step: that no page sits under a language the site does not
publish, that the home page and each of its five sections has its own page at its English path, that each page declares
the language of the prefix it sits under on its root element and marks no element with a language the site does not
publish, the parity of the languages it does, that each page that declares en-US reads as English, no paragraph or
list item of its main nor its main as a whole reading as Portuguese or Spanish by their function words (a block of
fewer than MIN_WORDS, 8 words, is never judged), the header and footer every page of one language shares, the internal
links and #anchors, the media budget, the poster image of every recording, the metadata search engines and link previews
read: each page's canonical address, description, and Open Graph tags, the sitemap that lists the pages, and the
robots.txt that points to it; the landing page: its primary call to action leads to harmflow-app on GitHub and comes
before the community edition's link to the build instructions, the page says that HarmFlow is coming to the Mac App
Store and links to no store page yet, and the text of its main names its audience: developers, on the Mac, who use
Claude Code or Codex; what two pages of each published language must say: the privacy policy's six parts, each with a
heading and text, its naming of Google Analytics, and what three of its parts say — that the app sends nothing to
HarmFlow and that what it keeps stays on the Mac, how long Google Analytics keeps the detailed data and that a return
visit does not extend that period, and that consent is withdrawn through the footer's link, by the label the page's own
footer gives it — and the support page's link to harmflow-app's issues, its saying that the issues are not support, and
no e-mail address on it; the user guide: that its index leads to its four parts in their order, that each part is a page
with its title and a paragraph of text, no longer a stub, and that each section under a part, a page one folder below
the part's, is linked from its part's page and has an h1 and a paragraph of text, no longer a stub; the technical
reference, the same way: that its index leads to its three parts in their order, and that each part is a page with its
title and a paragraph of text, no longer a stub; the root 404 page: that the tree has one, that its main says the page
was not found in a heading and links to the landing page, and that each of its links and assets is a path from the root,
which holds at any depth; the typefaces: that every @font-face rule takes its fonts only from WOFF2 files of the site
under /fonts/, that each font's folder holds its SIL Open Font License 1.1, and that the text and monospace stacks keep
the system's fonts as fallbacks; and the colors of the styles: each is one of the logo's fixed colors or a placeholder
until the palette is approved. It names each problem it finds on stderr, one per line, and exits 1 when it finds any.
The Checks workflow (.github/workflows/checks.yml) runs it on the checkout, and check-site-test.py proves each check on
a tree of its own that breaks it.

Usage: check-site.py [--languages en-US,pt-BR,es-ES] [ROOT]

ROOT is the folder GitHub Pages serves, site/ by default, so site/privacy/index.html is /privacy/. --languages names
the languages the site publishes, en-US only by default: the site is in English for now, and its translations come
back later under the prefixes LANGUAGES keeps for them.

The standard library only, and Python 3.9, so it runs on a Mac's own python3 as it does in CI.
"""

import colorsys
import os
import posixpath
import re
import sys
import unicodedata
from collections import OrderedDict
from html.parser import HTMLParser
from urllib.parse import unquote, urljoin, urlsplit

# en-US at the root, pt-BR under /pt-br/, es-ES under /es-es/, with the same English slugs in each.
LANGUAGES = (("en-US", ""), ("pt-BR", "pt-br/"), ("es-ES", "es-es/"))

# The languages the site publishes unless --languages names others. A page under another language's prefix fails.
PUBLISHED = ("en-US",)

# The paths the site serves at the root, in en-US, each with a page of its own: the home page and its five sections. A
# path may hold more pages below it; they do not stand for its own.
REQUIRED_PATHS = ("/", "/docs/guide/", "/docs/reference/", "/showroom/", "/privacy/", "/support/")

# The root 404 page is the one page that speaks for every language: GitHub Pages serves a custom 404 page only from
# the root. It has no versions to keep in parity, and belongs to no one language's shared header and footer.
ROOT_404 = "404.html"

# A link to one of these hosts is a link into the site, checked as a path of the tree.
SITE_HOSTS = ("harmflow.com",)

# The attributes that point to another file, by element. srcset holds a list of candidates.
LINK_ATTRIBUTES = {
    "a": ("href",),
    "area": ("href",),
    "link": ("href",),
    "img": ("src", "srcset"),
    "source": ("src", "srcset"),
    "script": ("src",),
    "iframe": ("src",),
    "audio": ("src",),
    "video": ("src", "poster"),
    "track": ("src",),
    "embed": ("src",),
    "object": ("data",),
    "input": ("src",),
}

# A header or footer inside one of these is that section's own, not the page's.
SECTIONING = ("article", "aside", "main", "nav", "section")

# Images, recordings, and sound, wherever they are in the tree. MB is 1,000,000 bytes, the stricter reading. A
# recording's poster is one of the images.
IMAGE_EXTENSIONS = (
    ".apng", ".avif", ".bmp", ".gif", ".heic", ".ico", ".jpeg", ".jpg", ".png", ".svg", ".tif", ".tiff", ".webp",
)
RECORDING_EXTENSIONS = (".avi", ".m4v", ".mkv", ".mov", ".mp4", ".mpeg", ".mpg", ".ogv", ".webm")
SOUND_EXTENSIONS = (".aac", ".flac", ".m4a", ".mp3", ".oga", ".ogg", ".opus", ".wav")
MEDIA_EXTENSIONS = IMAGE_EXTENSIONS + RECORDING_EXTENSIONS + SOUND_EXTENSIONS
MEDIA_FILE_LIMIT = 10 * 1000 * 1000
MEDIA_TOTAL_LIMIT = 300 * 1000 * 1000

# The address the site is published at: every canonical address, og:url, and sitemap entry starts with it.
ORIGIN = "https://harmflow.com"

# The Open Graph tags every page but the 404 page declares, so a link to it previews with a title, a text, and an image.
OPEN_GRAPH = ("og:type", "og:site_name", "og:title", "og:description", "og:url", "og:image")

# The landing page, at /. It leads with the full edition: its primary calls to action, the a elements of class cta,
# invite the visitor to follow the app on GitHub until its page on the Mac App Store exists, and its body says it is
# coming there. The community edition comes after them, through a link to the build instructions.
LANDING = "index.html"
LANDING_CTA = "https://github.com/harmflow/harmflow-app"
COMMUNITY_EDITION = "https://github.com/harmflow/harmflow-app#quick-start"
COMING_TO_THE_STORE = "coming to the mac app store"
STORE_HOST = "apps.apple.com"

# Whom the landing page's own text, the visible text of its main, says HarmFlow is for: developers, on the Mac, who use
# Claude Code or Codex, so it names both. The shared header and footer name them on every page, and the store's name
# holds "Mac" without naming the visitor's computer, so neither stands for it: the store's name is taken out first.
STORE_NAME = "mac app store"
DEVELOPERS = re.compile(r"\bdevelopers?\b")
THE_MAC = re.compile(r"\bmac\b")
HARNESSES = (("Claude Code", re.compile(r"\bclaude code\b")), ("Codex", re.compile(r"\bcodex\b")))

# The privacy policy's parts, by the id of each one's heading, and the support page, in every published language.
PRIVACY = "privacy/index.html"
PRIVACY_PARTS = (
    ("app", "the HarmFlow app"),
    ("website", "this website"),
    ("analytics", "analytics"),
    ("google", "how Google processes the data"),
    ("retention", "how long the data is kept"),
    ("withdraw", "withdrawing consent"),
)
SUPPORT = "support/index.html"

# What the privacy policy's parts and the support page's main must say, matched lowercased on their text joined across
# elements, as COMING_TO_THE_STORE is. Only en-US is published, so the words are en-US: another language gives its own
# with the work that publishes it. Each part's words: (the part's id, the problem when it lacks them, the words).
PRIVACY_SAYS = (
    ("app", "does not say that the app sends nothing to HarmFlow", "sends nothing to harmflow"),
    ("app", "does not say that what the app keeps stays on the Mac", "what it keeps stays on your mac"),
    ("retention", "does not give the period Google Analytics keeps the detailed data, two months", "two months"),
    (
        "retention",
        "does not say that a return visit does not extend that period",
        "does not extend that period when you come back",
    ),
    ("withdraw", "does not say that the link that reopens the choice is in the footer", "in the footer"),
)
NOT_SUPPORT = "the issues are not a support channel"

# The attribute of the footer's link that reopens the analytics choice, whose label the part on withdrawing names.
CONSENT_CHOICE = "data-consent-choice"

# Where the support page leads for defects and requests: this address, or one under it.
ISSUES = "https://github.com/harmflow/harmflow-app/issues"

# The user guide, in en-US at the root: its index, and its four parts, each a page of its own whose h1 is the part's
# title, in the order the index leads to them, and the sections under a part, each a page one folder below it. Only the
# main of each page is read: the header and footer every page shares link to the guide and hold text of their own.
GUIDE = "docs/guide/index.html"
GUIDE_PARTS = (
    ("/docs/guide/install/", "Installing HarmFlow"),
    ("/docs/guide/repository-access/", "Granting access to repositories"),
    ("/docs/guide/tasks/", "Creating tasks"),
    ("/docs/guide/executions/", "Reading executions"),
)
STUB = "This page is being written."

# The technical reference, in en-US at the root, read as the guide is: its index, and its three parts, each a page of
# its own whose h1 is the part's title, in the order the index leads to them.
REFERENCE = "docs/reference/index.html"
REFERENCE_PARTS = (
    ("/docs/reference/task-file/", "The task file"),
    ("/docs/reference/local-api/", "The local API"),
    ("/docs/reference/harnesses/", "The harnesses"),
)

# A plain e-mail address, name@domain.tld, in a page's visible text.
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")

# The headings, and the addresses of the landing page the 404 page's main may link to.
HEADINGS = ("h1", "h2", "h3", "h4", "h5", "h6")
LANDING_PAGE = ("/", ORIGIN + "/")

# Elements with no end tag, which never hold another, and the ones whose text no visitor reads.
VOID = (
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr",
)
HIDDEN = ("head", "script", "style", "template")

# The language of a page's text, read from its function words. A block of text is the text of a p or li element inside
# the main, or the whole main; the text of the elements of UNJUDGED is in none, since code, its output, and keys are in
# no human language. A block of fewer than MIN_WORDS words is never judged: too short to read a language from. One of
# at least that many reads as Portuguese, or Spanish, when it holds at least MIN_FOREIGN of that language's words and
# more of them than of the English ones.
UNJUDGED = ("code", "pre", "kbd")
TEXT_BLOCKS = ("p", "li")
MIN_WORDS = 8
MIN_FOREIGN = 2
# Words are letters only, compared lowercased with their accents: "don't" is "don" and "t", "en-US" is "en" and "us".
WORD = re.compile(r"[^\W\d_]+")
# Each list holds only words of its own language: the Portuguese and Spanish ones no word that is also English. A word
# common to two of the languages — "a", "no", "do", "me", "come", "as", "para", "que", "está" — is in none, nor is one
# that is an English word too ("el", "la", "lo", "sin", "con", "hay", "um", "num"), a language's tag ("en", "es"), or a
# piece a name, an address, or an abbreviation often splits into ("com", "os", "e", "al"): no such word tips a block.
# A word in more than one list would count for none of them.
ENGLISH_WORDS = """
    the and of to in is are was were be been being it its that this these those with on at by from or but not an
    which what when where who whom whose why how you your yours we our ours us they them their theirs his her him she
    there here have had does did will would can could should must if then than so all each every any into onto about
    after before over under between through without only also more most just very i my mine
""".split()
PORTUGUESE_WORDS = """
    não você vocês também uma umas isso isto essa esse essas esses aquele aquela dele dela deles delas nós eles
    elas ao aos às à pelo pela pelos pelas numa dos das seu sua seus suas meu minha então quando onde muito muita
    muitos muitas ainda já até após sem é são estão foi tem têm há pode podem mais nem ou na lhe lhes aqui agora
    depois sempre qual quais seja sejam fazer
""".split()
SPANISH_WORDS = """
    usted ustedes también los las del pero una unos unas muy más le les y su sus están esto eso ese esa esos
    esas aquel nosotros ellos ellas puede pueden cuando donde hacer tiene tienen mucha muchos muchas
    todavía ahora después aquí siempre cual cuál fue gracias
""".split()
FUNCTION_WORDS = (("English", ENGLISH_WORDS), ("Portuguese", PORTUGUESE_WORDS), ("Spanish", SPANISH_WORDS))

# The site's typefaces, each with the custom property of its stack and the generic family that ends it.
FONT_STACKS = (("Inter", "--font-text", "sans-serif"), ("JetBrains Mono", "--font-mono", "monospace"))

# The folder the fonts are served from, one folder per family, and the first four bytes of every WOFF2 file.
FONTS = "fonts/"
WOFF2_SIGNATURE = b"wOF2"

# The title line of the SIL Open Font License 1.1, which its full text carries.
OFL = "sil open font license version 1.1"

# The logo's colors, fixed whatever the palette becomes. Every other color of the styles is a placeholder until the
# palette is approved, declared once as a custom property of the :root block of PLACEHOLDERS. The rule reads every
# stylesheet under STYLES, and every <style> element and style attribute of the pages.
LOGO_COLORS = ("#22d3ee", "#8b5cf6", "#e040fb")
PLACEHOLDERS = "styles/site.css"
STYLES = "styles"

# CSS's named colors, which a value may write in place of a hex color. transparent, currentColor, and inherit are no
# color of their own, so the rule reads none of them.
_NAMED = """
    aliceblue f0f8ff antiquewhite faebd7 aqua 00ffff aquamarine 7fffd4 azure f0ffff beige f5f5dc bisque ffe4c4
    black 000000 blanchedalmond ffebcd blue 0000ff blueviolet 8a2be2 brown a52a2a burlywood deb887 cadetblue 5f9ea0
    chartreuse 7fff00 chocolate d2691e coral ff7f50 cornflowerblue 6495ed cornsilk fff8dc crimson dc143c cyan 00ffff
    darkblue 00008b darkcyan 008b8b darkgoldenrod b8860b darkgray a9a9a9 darkgreen 006400 darkgrey a9a9a9
    darkkhaki bdb76b darkmagenta 8b008b darkolivegreen 556b2f darkorange ff8c00 darkorchid 9932cc darkred 8b0000
    darksalmon e9967a darkseagreen 8fbc8f darkslateblue 483d8b darkslategray 2f4f4f darkslategrey 2f4f4f
    darkturquoise 00ced1 darkviolet 9400d3 deeppink ff1493 deepskyblue 00bfff dimgray 696969 dimgrey 696969
    dodgerblue 1e90ff firebrick b22222 floralwhite fffaf0 forestgreen 228b22 fuchsia ff00ff gainsboro dcdcdc
    ghostwhite f8f8ff gold ffd700 goldenrod daa520 gray 808080 green 008000 greenyellow adff2f grey 808080
    honeydew f0fff0 hotpink ff69b4 indianred cd5c5c indigo 4b0082 ivory fffff0 khaki f0e68c lavender e6e6fa
    lavenderblush fff0f5 lawngreen 7cfc00 lemonchiffon fffacd lightblue add8e6 lightcoral f08080 lightcyan e0ffff
    lightgoldenrodyellow fafad2 lightgray d3d3d3 lightgreen 90ee90 lightgrey d3d3d3 lightpink ffb6c1
    lightsalmon ffa07a lightseagreen 20b2aa lightskyblue 87cefa lightslategray 778899 lightslategrey 778899
    lightsteelblue b0c4de lightyellow ffffe0 lime 00ff00 limegreen 32cd32 linen faf0e6 magenta ff00ff maroon 800000
    mediumaquamarine 66cdaa mediumblue 0000cd mediumorchid ba55d3 mediumpurple 9370db mediumseagreen 3cb371
    mediumslateblue 7b68ee mediumspringgreen 00fa9a mediumturquoise 48d1cc mediumvioletred c71585
    midnightblue 191970 mintcream f5fffa mistyrose ffe4e1 moccasin ffe4b5 navajowhite ffdead navy 000080
    oldlace fdf5e6 olive 808000 olivedrab 6b8e23 orange ffa500 orangered ff4500 orchid da70d6 palegoldenrod eee8aa
    palegreen 98fb98 paleturquoise afeeee palevioletred db7093 papayawhip ffefd5 peachpuff ffdab9 peru cd853f
    pink ffc0cb plum dda0dd powderblue b0e0e6 purple 800080 rebeccapurple 663399 red ff0000 rosybrown bc8f8f
    royalblue 4169e1 saddlebrown 8b4513 salmon fa8072 sandybrown f4a460 seagreen 2e8b57 seashell fff5ee
    sienna a0522d silver c0c0c0 skyblue 87ceeb slateblue 6a5acd slategray 708090 slategrey 708090 snow fffafa
    springgreen 00ff7f steelblue 4682b4 tan d2b48c teal 008080 thistle d8bfd8 tomato ff6347 turquoise 40e0d0
    violet ee82ee wheat f5deb3 white ffffff whitesmoke f5f5f5 yellow ffff00 yellowgreen 9acd32
""".split()
NAMED_COLORS = dict(zip(_NAMED[::2], ("#" + value for value in _NAMED[1::2])))

# What a value says, once its comments, strings, and url()s are blanked out: no color is read in any of them.
CSS_COMMENT = re.compile(r"/\*.*?\*/", re.S)
CSS_STRING = re.compile(r"\"[^\"\n]*\"|'[^'\n]*'|\burl\([^)]*\)", re.I)
CSS_DECLARATION = re.compile(r"([-\w]+)\s*:([^;]*)")
# A color as a value writes it: hex of 3, 4, 6, or 8 digits, a color function, or a word that may be a named color.
# A word that is part of another, such as cyan in --logo-cyan, is no word of its own.
CSS_COLOR = re.compile(
    r"(?<![\w#-])(?:#(?P<hex>[0-9a-f]{8}|[0-9a-f]{6}|[0-9a-f]{3,4})(?![\w-])"
    r"|(?P<function>(?:rgba?|hsla?)\([^)]*\))"
    r"|(?P<word>[a-z][\w-]*))",
    re.I,
)


def language_of(rel):
    """The language of a page and its slug, the path it has in every language."""
    for language, prefix in LANGUAGES[1:]:
        if rel.startswith(prefix):
            return language, rel[len(prefix):]
    return LANGUAGES[0][0], rel


def url_of(rel):
    """The path a page is served at: privacy/index.html at /privacy/."""
    if rel == "index.html":
        return "/"
    if rel.endswith("/index.html"):
        return "/" + rel[: -len("index.html")]
    return "/" + rel


def resolve(page_url, ref):
    """The site path and #fragment a reference leads to, or None when it leads out of the site or nowhere."""
    ref = ref.strip()
    if not ref:
        return None
    parts = urlsplit(ref)
    if parts.scheme or parts.netloc:
        if parts.scheme not in ("", "http", "https") or parts.netloc.lower() not in SITE_HOSTS:
            return None
        path = parts.path or "/"
    else:
        path = urljoin(page_url, parts.path) if parts.path else page_url
    return path, unquote(parts.fragment)


def file_of(root, path):
    """The file of the tree a site path is served from, as GitHub Pages serves it, or None when there is none."""
    trailing = path.endswith("/")
    rel = posixpath.normpath(unquote(path).lstrip("/")) if path.strip("/") else ""
    if rel.startswith(".."):
        return None
    if rel in ("", "."):
        candidates = ["index.html"]
    elif trailing:
        candidates = [rel + "/index.html"]
    else:
        candidates = [rel, rel + ".html", rel + "/index.html"]
    for candidate in candidates:
        if os.path.isfile(os.path.join(root, candidate)):
            return candidate
    return None


def references(name, value):
    """The references an attribute holds: one, or each candidate of a srcset."""
    if name == "srcset":
        return [candidate.split()[0] for candidate in value.split(",") if candidate.strip()]
    return [value]


class Page(HTMLParser):
    """One HTML file: the ids its #anchors may name, the references it makes, its recordings, its header's and footer's
    tokens, its visible text, the outline its headings give that text, and the headings' text, the h1s' text, the links,
    the visible text, the paragraphs' text, and the text whose language is judged, by block, inside its main."""

    def __init__(self, rel):
        super().__init__(convert_charrefs=True)
        self.rel = rel
        self.url = url_of(rel)
        self.ids = set()
        self.links = []  # (line, attribute, reference)
        self.videos = []  # {"line", "src", "poster"}: poster is None with no attribute, "" with an empty one
        self._video = None
        self.raw_blocks = {}  # "header" or "footer": [token], each token a tag or a text
        self.canonical = None
        self.description = None
        self.open_graph = {}  # "og:title": its content
        self.anchors = []  # (line, href, is a primary call to action), each a element with an href, in the page's order
        self.hrefs = []  # (line, href), every href of the page, the head's included
        self.body_text = []  # the text of the body, what the visitor reads
        self.style_elements = []  # (line, css), the text of each <style> element from the line it starts on
        self.style_attributes = []  # (line, declarations), each style attribute on the line of its tag
        self._in_body = False
        self.declared = None  # the lang of the root element, "" when it has none
        self.marked = []  # (line, lang) of every other element with a lang
        self.text = []  # the visible text, a run of words per piece
        # In document order: ("heading", level, id, depth) where depth is the open elements' count around it,
        # ("text", text) for visible text outside any heading, and ("end", depth) when an element closes, depth after.
        self.outline = []
        self._open = []  # the open elements, outermost first
        self.main_headings = []  # each heading's text, inside main
        self.main_titles = []  # each h1's text, inside main
        self.main_links = []  # each a's or area's href, inside main
        self.main_text = []  # the text inside main
        self.main_paragraphs = []  # the text inside main's p elements
        self.judged_main = []  # the text inside main, but for the UNJUDGED elements'
        self.text_blocks = []  # (line, [text]) of each p and li inside main: its own text, but a nested one's
        self._blocks = []  # (the open elements' count with it, its index in text_blocks) of each open p and li
        self._in_style = False
        self._sectioning = 0
        self._capture = None
        self._depth = 0
        self._tokens = []
        self._main = 0
        self._heading = None
        self._heading_text = []

    def handle_starttag(self, tag, attrs):
        line = self.getpos()[0]
        named = dict(attrs)
        if tag in HEADINGS:
            self.outline.append(("heading", int(tag[1]), named.get("id"), len(self._open)))
        if tag not in VOID:
            self._open.append(tag)
        if tag == "link" and (named.get("rel") or "").lower() == "canonical" and self.canonical is None:
            self.canonical = named.get("href") or ""
        if tag == "meta" and (named.get("name") or "").lower() == "description" and self.description is None:
            self.description = (named.get("content") or "").strip()
        if tag == "meta" and (named.get("property") or "").startswith("og:"):
            self.open_graph.setdefault(named["property"], (named.get("content") or "").strip())
        if tag == "body":
            self._in_body = True
        if tag == "style":
            self._in_style = True
        if named.get("style") is not None:
            self.style_attributes.append((line, named["style"]))
        if named.get("href") is not None:
            self.hrefs.append((line, named["href"]))
            if tag == "a":
                self.anchors.append((line, named["href"].strip(), "cta" in (named.get("class") or "").split()))
        if tag == "html" and self.declared is None:
            self.declared = (named.get("lang") or "").strip()
        elif named.get("lang") is not None:
            self.marked.append((line, named["lang"].strip()))
        if tag == "main":
            self._main += 1
        if self._main and tag in HEADINGS and self._heading is None:
            self._heading, self._heading_text = tag, []
        if self._main and tag in TEXT_BLOCKS:
            self._blocks.append((len(self._open), len(self.text_blocks)))
            self.text_blocks.append((line, []))
        if self._main and tag in ("a", "area") and named.get("href") is not None:
            self.main_links.append(named["href"].strip())
        if tag == "video":
            # A bare poster attribute has no value: as empty as poster="".
            poster = (named.get("poster") or "").strip() if "poster" in named else None
            self._video = {"line": line, "src": (named.get("src") or "").strip(), "poster": poster}
            self.videos.append(self._video)
        if tag == "source" and self._video is not None and not self._video["src"]:
            # A video with no src of its own plays its first <source>.
            self._video["src"] = (named.get("src") or "").strip()
        for name, value in attrs:
            if value is None:
                continue
            if name == "id" or (tag == "a" and name == "name"):
                self.ids.add(value)
            if name in LINK_ATTRIBUTES.get(tag, ()):
                for ref in references(name, value):
                    self.links.append((line, name, ref))
        if self._capture:
            self._tokens.append(("start", tag, attrs))
            if tag == self._capture:
                self._depth += 1
        elif tag in ("header", "footer") and self._sectioning == 0 and tag not in self.raw_blocks:
            self._capture, self._depth, self._tokens = tag, 1, [("start", tag, attrs)]
        if tag in SECTIONING:
            self._sectioning += 1

    def handle_endtag(self, tag):
        # An end tag closes its element and any left open inside it, as a browser does; one with no open element is
        # ignored.
        if tag in self._open:
            while self._open.pop() != tag:
                pass
            self.outline.append(("end", len(self._open)))
            while self._blocks and self._blocks[-1][0] > len(self._open):
                self._blocks.pop()
        if tag == "video":
            self._video = None
        if tag == "style":
            self._in_style = False
        if tag in SECTIONING and self._sectioning:
            self._sectioning -= 1
        if tag == self._heading:
            heading = " ".join(" ".join(self._heading_text).split())
            self.main_headings.append(heading)
            if tag == "h1":
                self.main_titles.append(heading)
            self._heading = None
        if tag == "main" and self._main:
            self._main -= 1
        if self._capture:
            self._tokens.append(("end", tag, None))
            if tag == self._capture:
                self._depth -= 1
                if self._depth == 0:
                    self.raw_blocks[self._capture] = self._tokens
                    self._capture = None

    def handle_data(self, data):
        if self._in_style:
            self.style_elements.append((self.getpos()[0], data))
        text = " ".join(data.split())
        if self._heading and text:
            self._heading_text.append(text)
        if self._capture and text:
            self._tokens.append(("text", text, None))
        if self._in_body and text:
            self.body_text.append(text)
        if text and not any(tag in HIDDEN for tag in self._open):
            self.text.append(text)
            if self._main:
                self.main_text.append(text)
                if "p" in self._open:
                    self.main_paragraphs.append(text)
                if not any(tag in UNJUDGED for tag in self._open):
                    self.judged_main.append(text)
                    if self._blocks:
                        self.text_blocks[self._blocks[-1][1]][1].append(text)
            if not any(tag in HEADINGS for tag in self._open):
                self.outline.append(("text", text))


def read_page(root, rel):
    page = Page(rel)
    with open(os.path.join(root, rel), encoding="utf-8", errors="replace") as f:
        page.feed(f.read())
    page.close()
    return page


def site_files(root, skip_hidden):
    """Every file of the tree, as a path relative to ROOT, sorted. .git is never read; with skip_hidden, no path
    component that starts with a dot is either, since those hold no page."""
    found = []
    for directory, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d != ".git" and not (skip_hidden and d.startswith(".")))
        for name in files:
            if skip_hidden and name.startswith("."):
                continue
            found.append(os.path.relpath(os.path.join(directory, name), root).replace(os.sep, "/"))
    return sorted(found)


def check_unpublished(pages, published):
    """A page under the prefix of a language the site does not publish names the page and the language."""
    problems = []
    for rel in pages:
        language, _ = language_of(rel)
        if language not in published:
            problems.append(
                "unpublished: %s is a %s page, and the site publishes only %s" % (rel, language, ", ".join(published))
            )
    return problems


def check_declared_languages(pages, published):
    """Every page's root element declares the language of the prefix it sits under, en-US at the root and so the root
    404 page too, and no element inside a page is marked with a language the script knows and the site does not
    publish. Languages are BCP 47 tags, compared without regard to case; an empty lang declares none, and a lang the
    script does not know is left alone."""
    problems = []
    unpublished = set(language.lower() for language, _ in LANGUAGES if language not in published)
    for rel, page in pages.items():
        expected, _ = language_of(rel)
        if not page.declared:
            problems.append("languages: %s declares no language on its root element; it is %s" % (rel, expected))
        elif page.declared.lower() != expected.lower():
            problems.append("languages: %s declares %s on its root element, not %s" % (rel, page.declared, expected))
        for line, lang in page.marked:
            if lang.lower() in unpublished:
                problems.append(
                    "languages: %s:%d: an element is marked %s, a language the site does not publish"
                    % (rel, line, lang)
                )
    return problems


def counted_words():
    """Each language's function words that are no other language's: a word in two lists counts for none."""
    counted = OrderedDict()
    for language, words in FUNCTION_WORDS:
        others = set(word for other, more in FUNCTION_WORDS if other != language for word in more)
        counted[language] = set(words) - others
    return counted


def reads_as(texts, counted):
    """The language TEXTS read as when it is not English — Portuguese or Spanish — or None: when they hold fewer than
    MIN_WORDS words, or no other language's words number MIN_FOREIGN and outnumber the English ones."""
    words = WORD.findall(unicodedata.normalize("NFC", " ".join(texts)).lower())
    if len(words) < MIN_WORDS:
        return None
    counts = OrderedDict((language, sum(word in known for word in words)) for language, known in counted.items())
    english = counts.pop("English")
    found = [(count, language) for language, count in counts.items() if count >= MIN_FOREIGN and count > english]
    # The language with the most words; Portuguese, the first, on a tie.
    return max(found, key=lambda f: f[0])[1] if found else None


def check_text_languages(pages):
    """The text of every page that declares en-US reads as English. Each paragraph and list item of its main — a p or
    li element, its own text without that of a p or li inside it — and its main as a whole are judged, the text of
    code, pre, and kbd elements left out. A block of fewer than MIN_WORDS (8) words is never judged; one of at least
    that many fails when its Portuguese words, or its Spanish words, number at least MIN_FOREIGN (2) and outnumber its
    English function words. The words of each language are short lists of function words, ENGLISH_WORDS,
    PORTUGUESE_WORDS, and SPANISH_WORDS, compared lowercased after splitting on anything that is not a letter, accents
    kept; a word in more than one list counts for none, so a name or a borrowed word tips no block."""
    problems = []
    counted = counted_words()
    for rel, page in pages.items():
        if (page.declared or "").lower() != "en-us":
            continue
        for line, texts in page.text_blocks:
            language = reads_as(texts, counted)
            if language:
                problems.append("text language: %s:%d: a paragraph reads as %s" % (rel, line, language))
        language = reads_as(page.judged_main, counted)
        if language:
            problems.append("text language: %s: its main reads as %s" % (rel, language))
    return problems


def check_paths(pages):
    """Each required path has its own page; a missing one names the path and the file it expects there. A tree with no
    page needs none."""
    if not pages:
        return []
    problems = []
    for path in REQUIRED_PATHS:
        rel = path.lstrip("/") + "index.html"
        if rel not in pages:
            problems.append("paths: %s has no page: %s is missing" % (path, rel))
    return problems


def check_parity(pages, published):
    """A page of one published language with no version at the same slug in another names the missing file."""
    problems = []
    missing = OrderedDict()
    for rel in pages:
        if rel == ROOT_404:
            continue
        language, slug = language_of(rel)
        if language not in published:
            continue
        for other, prefix in LANGUAGES:
            if other in published and other != language and prefix + slug not in pages:
                missing.setdefault(prefix + slug, (other, rel))
    for absent, (language, source) in missing.items():
        problems.append("parity: %s is missing: %s has no %s version" % (absent, source, language))
    return problems


def block_tokens(root, page, block, published):
    """A page's header or footer, as tokens that compare equal when the markup is the same: whitespace collapsed,
    attributes sorted, references resolved to site paths, and a link to this page in another language — the
    language selector's, which differs on every page by design — replaced by the name of that language."""
    raw = page.raw_blocks.get(block)
    if raw is None:
        return ("(no %s)" % block,)
    language, slug = language_of(page.rel)
    versions = {prefix + slug: other for other, prefix in LANGUAGES if other in published and other != language}
    tokens = []
    for kind, tag, attrs in raw:
        if kind == "text":
            tokens.append(tag)
        elif kind == "end":
            tokens.append("</%s>" % tag)
        else:
            shown = []
            for name, value in sorted(attrs, key=lambda a: a[0]):
                if value is not None and name in LINK_ATTRIBUTES.get(tag, ()) and name != "srcset":
                    target = resolve(page.url, value)
                    if target is not None:
                        path, fragment = target
                        version = versions.get(file_of(root, path) or "")
                        value = "(this page in %s)" % version if version else path
                        if fragment:
                            value += "#" + fragment
                shown.append(name if value is None else '%s="%s"' % (name, " ".join(value.split())))
            tokens.append("<%s>" % " ".join([tag] + shown))
    return tuple(tokens)


def first_difference(reference, tokens):
    for i in range(max(len(reference), len(tokens))):
        theirs = reference[i] if i < len(reference) else "(the end)"
        mine = tokens[i] if i < len(tokens) else "(the end)"
        if theirs != mine:
            return "%s where the others have %s" % (clip(mine), clip(theirs))
    return ""


def clip(text, width=100):
    return text if len(text) <= width else text[: width - 1] + "…"


def check_shared_blocks(root, pages, published):
    """Within one language, every page's header and footer is the same; the pages that differ from the version most of
    them share are named, and every page is when no version is shared by most."""
    problems = []
    for language in published:
        members = [rel for rel in pages if rel != ROOT_404 and language_of(rel)[0] == language]
        for block in ("header", "footer"):
            versions = OrderedDict()
            for rel in members:
                versions.setdefault(block_tokens(root, pages[rel], block, published), []).append(rel)
            if len(versions) < 2:
                continue
            ranked = sorted(versions.items(), key=lambda v: -len(v[1]))
            if len(ranked[0][1]) > len(ranked[1][1]):
                reference, shared = ranked[0]
                for tokens, rels in ranked[1:]:
                    for rel in rels:
                        problems.append(
                            "shared blocks: %s: its %s differs from the other %s pages' (%s): %s"
                            % (rel, block, language, ", ".join(shared), first_difference(reference, tokens))
                        )
            else:
                for _, rels in ranked:
                    for rel in rels:
                        problems.append(
                            "shared blocks: %s: the %s pages' %ss differ, and no version is shared by most: %s"
                            % (rel, language, block, " | ".join(", ".join(r) for _, r in ranked))
                        )
    return problems


def check_links(root, pages):
    """Every reference into the site leads to a file of the tree, and every #anchor to an id of its page."""
    problems = []
    # A page outside the site's own, read for its ids, joins pages: iterate over the ones there at the start.
    for rel, page in list(pages.items()):
        for line, _, ref in page.links:
            target = resolve(page.url, ref)
            if target is None:
                continue
            path, fragment = target
            found = file_of(root, path)
            if found is None:
                problems.append("links: %s:%d: %s leads to no file" % (rel, line, ref))
                continue
            if not fragment or fragment.lower() == "top" or not found.endswith(".html"):
                continue
            if found not in pages:
                pages[found] = read_page(root, found)
            if fragment not in pages[found].ids:
                problems.append("links: %s:%d: %s names no id of %s" % (rel, line, ref, found))
    return problems


def check_media(root):
    """No media file over 10 MB, and no more than 300 MB of them together."""
    problems = []
    total = 0
    count = 0
    for rel in site_files(root, skip_hidden=False):
        if os.path.splitext(rel)[1].lower() not in MEDIA_EXTENSIONS:
            continue
        size = os.path.getsize(os.path.join(root, rel))
        total += size
        count += 1
        if size > MEDIA_FILE_LIMIT:
            problems.append(
                "media: %s is %s bytes, over the 10 MB limit for one media file (%s bytes)"
                % (rel, format(size, ","), format(MEDIA_FILE_LIMIT, ","))
            )
    if total > MEDIA_TOTAL_LIMIT:
        problems.append(
            "media: the %d media files total %s bytes, over the 300 MB limit for all media together (%s bytes)"
            % (count, format(total, ","), format(MEDIA_TOTAL_LIMIT, ","))
        )
    return problems, count, total


def check_posters(root, pages):
    """Every recording on a page has a poster, and its poster is an image by its extension. A poster that names no
    file of the tree is the link rule's failure, not this one's, whatever its extension."""
    problems = []
    for rel, page in pages.items():
        for video in page.videos:
            where = "posters: %s:%d: the video %s" % (rel, video["line"], video["src"] or "(with no source)")
            poster = video["poster"]
            target = resolve(page.url, poster) if poster else None
            if poster is None:
                problems.append("%s has no poster" % where)
            elif not poster:
                problems.append("%s has an empty poster" % where)
            elif target is not None and file_of(root, target[0]) is None:
                continue
            elif posixpath.splitext(unquote(urlsplit(poster).path))[1].lower() not in IMAGE_EXTENSIONS:
                problems.append("%s has the poster %s, which is not an image file" % (where, poster))
    return problems


def address_of(rel):
    """The address a page is published at: privacy/index.html at https://harmflow.com/privacy/."""
    return ORIGIN + url_of(rel)


def check_metadata(root, pages):
    """Every page but the 404 page declares its canonical address, a description, and the Open Graph tags, with
    og:url its canonical address and og:image an image of the site; sitemap.xml lists exactly those pages, and
    robots.txt points to it. A tree with no such page needs neither file."""
    problems = []
    expected = OrderedDict((address_of(rel), rel) for rel in pages if rel != ROOT_404)
    for address, rel in expected.items():
        page = pages[rel]
        if not page.canonical:
            problems.append("metadata: %s declares no canonical address; it is %s" % (rel, address))
        elif page.canonical != address:
            problems.append("metadata: %s: its canonical address is %s, not %s" % (rel, page.canonical, address))
        if not page.description:
            problems.append("metadata: %s has no description" % rel)
        missing = [name for name in OPEN_GRAPH if not page.open_graph.get(name)]
        if missing:
            problems.append("metadata: %s has no %s" % (rel, ", ".join(missing)))
        url = page.open_graph.get("og:url")
        if url and url != address:
            problems.append("metadata: %s: its og:url is %s, not its canonical address %s" % (rel, url, address))
        image = page.open_graph.get("og:image")
        if image and not (image.startswith(ORIGIN + "/") and file_of(root, image[len(ORIGIN):])):
            problems.append("metadata: %s: its og:image %s is no image of %s" % (rel, image, ORIGIN))
    if not expected:
        return problems
    sitemap = os.path.join(root, "sitemap.xml")
    if not os.path.isfile(sitemap):
        problems.append("metadata: sitemap.xml is missing")
    else:
        with open(sitemap, encoding="utf-8", errors="replace") as f:
            listed = [loc.strip() for loc in re.findall(r"<loc>(.*?)</loc>", f.read(), flags=re.S)]
        for address, rel in expected.items():
            if address not in listed:
                problems.append("metadata: sitemap.xml does not list %s (%s)" % (address, rel))
        for address in listed:
            if address not in expected:
                problems.append("metadata: sitemap.xml lists %s, which is no page of the site" % address)
    robots = os.path.join(root, "robots.txt")
    pointer = "Sitemap: %s/sitemap.xml" % ORIGIN
    if not os.path.isfile(robots):
        problems.append("metadata: robots.txt is missing")
    else:
        with open(robots, encoding="utf-8", errors="replace") as f:
            if pointer not in [line.strip() for line in f]:
                problems.append("metadata: robots.txt has no line %s" % pointer)
    return problems


def check_landing(pages):
    """The landing page leads with the full edition: it has a primary call to action, and each one leads to the app on
    GitHub; the community edition's link to the build instructions is there, after the first of them and none of them;
    the page's body says HarmFlow is coming to the Mac App Store; no href, the header's and footer's included, leads
    to the Mac App Store, where HarmFlow has no page yet; and the page names its audience: the text of its main alone
    says it is for developers, names the Mac outside the Mac App Store's name, and names Claude Code and Codex, in any
    case and across elements. A tree with no landing page has none of this to check."""
    page = pages.get(LANDING)
    if page is None:
        return []
    problems = []
    own_text = " ".join(page.main_text).lower()
    if not DEVELOPERS.search(own_text):
        problems.append("landing: %s does not say that HarmFlow is for developers" % LANDING)
    if not THE_MAC.search(own_text.replace(STORE_NAME, " ")):
        problems.append("landing: %s does not name the Mac, other than in the Mac App Store's name" % LANDING)
    for name, pattern in HARNESSES:
        if not pattern.search(own_text):
            problems.append("landing: %s does not name %s" % (LANDING, name))
    ctas = [(line, href) for line, href, cta in page.anchors if cta]
    if not ctas:
        problems.append("landing: %s has no primary call to action (an a.cta)" % LANDING)
    for line, href in ctas:
        if href != LANDING_CTA:
            problems.append(
                "landing: %s:%d: its primary call to action leads to %s, not %s" % (LANDING, line, href, LANDING_CTA)
            )
    # Positions in the page's order, not lines, which two links may share.
    first_cta = next((i for i, (_, _, cta) in enumerate(page.anchors) if cta), None)
    community = [(i, line, cta) for i, (line, href, cta) in enumerate(page.anchors) if href == COMMUNITY_EDITION]
    if not community:
        problems.append(
            "landing: %s has no link to the community edition's build instructions, %s" % (LANDING, COMMUNITY_EDITION)
        )
    for _, line, cta in community:
        if cta:
            problems.append(
                "landing: %s:%d: the community edition's link is itself a primary call to action, so it leads"
                % (LANDING, line)
            )
    if community and first_cta is not None and community[0][0] < first_cta:
        problems.append(
            "landing: %s:%d: the community edition's link comes before the first primary call to action (line %d), "
            "so it leads" % (LANDING, community[0][1], page.anchors[first_cta][0])
        )
    if COMING_TO_THE_STORE not in " ".join(page.body_text).lower():
        problems.append("landing: %s does not say that HarmFlow is coming to the Mac App Store" % LANDING)
    for line, href in page.hrefs:
        if (urlsplit(href.strip()).hostname or "") == STORE_HOST:
            problems.append(
                "landing: %s:%d: %s leads to the Mac App Store, where HarmFlow has no page yet" % (LANDING, line, href)
            )
    return problems


def part_has_text(page, part_id):
    """Whether a part has visible text, outside any heading, between its heading and the next heading of any level, or
    the end of the element that holds its heading: a lower heading's text is its own part's, not this one's. None when
    no heading has the part's id."""
    for i, event in enumerate(page.outline):
        if event[0] == "heading" and event[2] == part_id:
            depth = event[3]
            for later in page.outline[i + 1 :]:
                if later[0] == "text":
                    return True
                if later[0] == "heading":
                    return False
                if later[0] == "end" and later[1] < depth:
                    return False
            return False
    return None


def part_text(page, part_id):
    """A part's visible text outside any heading, joined with spaces and lowercased, between its heading and the next
    heading of the same or a higher level, or the end of the element that holds its heading: unlike part_has_text, a
    lower heading's text is this part's too. None when no heading has the part's id."""
    for i, event in enumerate(page.outline):
        if event[0] == "heading" and event[2] == part_id:
            level, depth = event[1], event[3]
            texts = []
            for later in page.outline[i + 1 :]:
                if later[0] == "text":
                    texts.append(later[1])
                elif later[0] == "heading" and later[1] <= level:
                    break
                elif later[0] == "end" and later[1] < depth:
                    break
            return " ".join(texts).lower()
    return None


def consent_label(page):
    """The label of the link in the page's own footer that reopens the analytics choice, the a with
    data-consent-choice, its text joined across elements; None when the footer has no such link."""
    tokens = page.raw_blocks.get("footer") or []
    for i, (kind, tag, attrs) in enumerate(tokens):
        # A bare attribute has no value: data-consent-choice is found by its name.
        if kind == "start" and tag == "a" and any(name == CONSENT_CHOICE for name, _ in attrs):
            label = []
            for later_kind, text, _ in tokens[i + 1 :]:
                if later_kind == "end" and text == "a":
                    break
                if later_kind == "text":
                    label.append(text)
            return " ".join(label)
    return None


def published_pages(pages, published, slug):
    """The page at SLUG in each published language the tree holds."""
    return [rel for rel in pages if language_of(rel)[1] == slug and language_of(rel)[0] in published]


def check_privacy(pages, published):
    """Each published language's privacy policy has a heading for each of its six parts, by the part's id, with text
    after it, and names Google Analytics. Each part with a heading and text says what PRIVACY_SAYS gives it: the part
    on the app, that the app sends nothing to HarmFlow and that what it keeps stays on the Mac; the part on retention,
    the two months Google Analytics keeps the detailed data and that a return visit does not extend them; and the part
    on withdrawing consent, that the link that reopens the choice is in the footer, by the label the page's own footer
    gives the a with data-consent-choice, which fails when the footer has no such link. A part's text runs to the next
    heading of the same or a higher level (part_text). A tree with no privacy policy has nothing to check."""
    problems = []
    names = dict(PRIVACY_PARTS)
    for rel in published_pages(pages, published, PRIVACY):
        page = pages[rel]
        said = {}  # each part's text, for the parts with a heading and text after it
        for part_id, part in PRIVACY_PARTS:
            has_text = part_has_text(page, part_id)
            if has_text is None:
                problems.append("privacy: %s has no heading with the id %s, for its part on %s" % (rel, part_id, part))
            elif not has_text:
                problems.append(
                    "privacy: %s: its part on %s (#%s) has no text after its heading" % (rel, part, part_id)
                )
            else:
                said[part_id] = part_text(page, part_id)
        if "Google Analytics" not in " ".join(page.text):
            problems.append("privacy: %s does not name Google Analytics" % rel)
        for part_id, missing, words in PRIVACY_SAYS:
            if part_id in said and words not in said[part_id]:
                problems.append("privacy: %s: its part on %s (#%s) %s" % (rel, names[part_id], part_id, missing))
        if "withdraw" in said:
            label = consent_label(page)
            if not label:
                problems.append(
                    "privacy: %s: its footer has no labeled link with %s that reopens the choice, so its part on "
                    "withdrawing consent (#withdraw) names no control the visitor can find" % (rel, CONSENT_CHOICE)
                )
            elif label.lower() not in said["withdraw"]:
                problems.append(
                    'privacy: %s: its part on withdrawing consent (#withdraw) does not name "%s", the label of the '
                    "footer's link that reopens the choice" % (rel, label)
                )
    return problems


def check_support(pages, published):
    """Each published language's support page links to harmflow-app's issues, or to an address under them, says in the
    visible text of its main that the issues are not support (NOT_SUPPORT, in any case and across elements), and gives
    no e-mail address, by a mailto: link or in its text. Only the support page is read for an address; a tree with no
    support page has nothing to check."""
    problems = []
    for rel in published_pages(pages, published, SUPPORT):
        page = pages[rel]
        hrefs = [href for _, href, _ in page.anchors]
        if not any(href == ISSUES or href.startswith((ISSUES + "/", ISSUES + "?", ISSUES + "#")) for href in hrefs):
            problems.append("support: %s has no link to %s" % (rel, ISSUES))
        if NOT_SUPPORT not in " ".join(page.main_text).lower():
            problems.append("support: %s does not say that the issues are not support" % rel)
        addresses = OrderedDict()
        for href in hrefs:
            if href.lower().startswith("mailto:"):
                addresses.setdefault(unquote(href[len("mailto:") :].split("?")[0]) or href, None)
        for address in EMAIL.findall(" ".join(page.text)):
            addresses.setdefault(address, None)
        for address in addresses:
            problems.append("support: %s gives the e-mail address %s; the support page gives none" % (rel, address))
    return problems


def served_path(path):
    """The path the page a link leads to is served at: /docs/guide/install, and its index.html, at
    /docs/guide/install/."""
    if path.endswith("/index.html"):
        path = path[: -len("index.html")]
    return path if path.endswith("/") else path + "/"


def check_parts(pages, rule, index_rel, parts):
    """The index INDEX_REL leads to PARTS, in their order, by the links of its main, with other links allowed between
    them; each part is a page whose main's h1 is the part's title, with a paragraph of text after it, and no longer the
    stub. Each problem is named under RULE. A tree with no such index has none of this to check: the paths rule names
    its missing index."""
    index = pages.get(index_rel)
    if index is None:
        return []
    problems = []
    titles = OrderedDict(parts)
    linked = []  # each part's path, in the order the index's main first links to it
    for href in index.main_links:
        target = resolve(index.url, href)
        path = served_path(target[0]) if target is not None else None
        if path in titles and path not in linked:
            linked.append(path)
    for path, title in parts:
        if path not in linked:
            problems.append("%s: %s: its main does not link to %s (%s)" % (rule, index_rel, path, title))
    expected = [path for path in titles if path in linked]
    for found, wanted in zip(linked, expected):
        if found != wanted:
            problems.append(
                "%s: %s: its main links to %s (%s) before %s (%s), out of the parts' order"
                % (rule, index_rel, found, titles[found], wanted, titles[wanted])
            )
            break
    for path, title in parts:
        rel = path.lstrip("/") + "index.html"
        page = pages.get(rel)
        if page is None:
            problems.append("%s: %s (%s) has no page: %s is missing" % (rule, path, title, rel))
            continue
        if not page.main_titles:
            problems.append('%s: %s: its main has no h1; it is "%s"' % (rule, rel, title))
        elif page.main_titles[0] != title:
            problems.append('%s: %s: its h1 is "%s", not "%s"' % (rule, rel, page.main_titles[0], title))
        if STUB in " ".join(page.main_text):
            problems.append('%s: %s still reads "%s"' % (rule, rel, STUB))
        elif not page.main_paragraphs:
            problems.append("%s: %s: its main has no paragraph of text beyond its heading" % (rule, rel))
    return problems


def check_guide(pages):
    """The guide's index leads to its four parts, in their order, and each part is a page with its title and a
    paragraph of text, no longer the stub (check_parts)."""
    return check_parts(pages, "guide", GUIDE, GUIDE_PARTS)


def check_reference(pages):
    """The technical reference's index leads to its three parts — the task file, the local API, and the harnesses — in
    their order, by the links of its main in any form that leads to them, with other links allowed between them; each
    part is a page whose main's h1 is the part's title, with a paragraph of text after it, and no longer the stub. Only
    the main of each page is read: the header and footer every page shares link to the reference and hold text of their
    own. A tree with no reference index has none of this to check (check_parts)."""
    return check_parts(pages, "reference", REFERENCE, REFERENCE_PARTS)


def check_guide_sections(pages):
    """Each section of the guide, a page one folder below a part's, docs/guide/<part>/<slug>/index.html, is linked to
    by its part's main, in any form that leads to it, and has an h1 in its main and a paragraph of text after it, no
    longer the stub. The sections are found by the shape of their path, so a section added later is checked as it is;
    a part with none has none to check, and a tree with no guide index has nothing. A part with no page is
    check_guide's to name, and adds no section problem."""
    if GUIDE not in pages:
        return []
    problems = []
    parts = [path.lstrip("/") for path, _ in GUIDE_PARTS]
    for rel, page in pages.items():
        part = next((path for path in parts if rel.startswith(path)), None)
        if part is None or not rel.endswith("/index.html") or rel[len(part) :].count("/") != 1:
            continue
        part_rel = part + "index.html"
        part_page = pages.get(part_rel)
        if part_page is not None:
            linked = set()
            for href in part_page.main_links:
                target = resolve(part_page.url, href)
                if target is not None:
                    linked.add(served_path(target[0]))
            if page.url not in linked:
                problems.append("guide: %s: its part's page %s does not link to it" % (rel, part_rel))
        if not page.main_titles:
            problems.append("guide: %s: its main has no h1" % rel)
        if STUB in " ".join(page.main_text):
            problems.append('guide: %s still reads "%s"' % (rel, STUB))
        elif not page.main_paragraphs:
            problems.append("guide: %s: its main has no paragraph of text beyond its heading" % rel)
    return problems


def check_not_found(root, pages):
    """A tree that holds pages has a 404.html at its root, whose main says in a heading that the page was not found
    and links to the landing page, and whose every link and asset is a path from the root, an absolute URL, or an
    #anchor: GitHub Pages answers every missing path with this one file, at any depth, where a relative path breaks."""
    if not pages:
        return []
    if not os.path.isfile(os.path.join(root, ROOT_404)):
        return ["not found: %s is missing: GitHub Pages serves a custom 404 page only from the root" % ROOT_404]
    page = pages[ROOT_404]
    problems = []
    if not any("not found" in heading.lower() for heading in page.main_headings):
        problems.append("not found: %s: its main has no heading that says the page was not found" % ROOT_404)
    if not any(href in LANDING_PAGE for href in page.main_links):
        problems.append(
            "not found: %s: its main has no link to the landing page (%s)" % (ROOT_404, " or ".join(LANDING_PAGE))
        )
    for line, name, ref in page.links:
        ref = ref.strip()
        if not ref or ref.startswith(("/", "#")) or urlsplit(ref).scheme:
            continue
        problems.append(
            'not found: %s:%d: %s="%s" is a relative path, which breaks at a missing path\'s depth; '
            "make it a path from the root" % (ROOT_404, line, name, ref)
        )
    return problems


def stylesheets(root):
    """Every stylesheet of the tree, as a path relative to ROOT, with its text, its comments removed."""
    sheets = OrderedDict()
    for rel in site_files(root, skip_hidden=True):
        if rel.endswith(".css"):
            with open(os.path.join(root, rel), encoding="utf-8", errors="replace") as f:
                sheets[rel] = re.sub(r"/\*.*?\*/", "", f.read(), flags=re.S)
    return sheets


def split_list(value):
    """The items of a comma-separated CSS value; a comma inside parentheses or quotes separates nothing."""
    items, current, depth, quote = [], "", 0, None
    for char in value:
        if quote:
            if char == quote:
                quote = None
        elif char in "\"'":
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif char == "," and depth == 0:
            items.append(current.strip())
            current = ""
            continue
        current += char
    if current.strip():
        items.append(current.strip())
    return items


def unquote_css(value):
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def check_font_faces(root, sheets):
    """Every @font-face rule takes its src only from .woff2 files of the site under /fonts/, each with the hint
    format("woff2"), and each a file of the tree that starts with the WOFF2 signature."""
    problems = []
    for rel, text in sheets.items():
        for body in re.findall(r"@font-face\s*\{([^}]*)\}", text):
            family = re.search(r"(?:^|;)\s*font-family\s*:\s*([^;]+)", body)
            src = re.search(r"(?:^|;)\s*src\s*:\s*([^;]+)", body)
            rule = "fonts: %s: the %s rule" % (rel, unquote_css(family.group(1)) if family else "(no font-family)")
            sources = split_list(src.group(1)) if src else []
            if not sources:
                problems.append("%s has no src" % rule)
            for source in sources:
                url = re.match(r"url\(\s*(['\"]?)(.*?)\1\s*\)\s*(.*)$", source, flags=re.S)
                if not url:
                    problems.append("%s takes %s, which is no file of the site" % (rule, clip(source)))
                    continue
                ref = url.group(2)
                hint = re.match(r"format\(\s*(['\"]?)(.*?)\1\s*\)", url.group(3))
                parts = urlsplit(ref)
                if parts.scheme or parts.netloc:
                    problems.append("%s takes %s from another host" % (rule, ref))
                    continue
                path = urljoin(url_of(rel), parts.path)
                if not path.startswith("/" + FONTS) or not path.endswith(".woff2"):
                    problems.append("%s takes %s, which is not a .woff2 file under /%s" % (rule, ref, FONTS))
                if not hint or hint.group(2).lower() != "woff2":
                    problems.append('%s takes %s without format("woff2")' % (rule, ref))
                file = posixpath.normpath(unquote(path).lstrip("/"))
                if file.startswith("..") or not os.path.isfile(os.path.join(root, file)):
                    problems.append("%s takes %s, which is no file of the site" % (rule, ref))
                    continue
                if path.endswith(".woff2"):
                    with open(os.path.join(root, file), "rb") as f:
                        if f.read(len(WOFF2_SIGNATURE)) != WOFF2_SIGNATURE:
                            problems.append(
                                "%s takes %s, which is not a WOFF2 file: it does not start with %s"
                                % (rule, ref, WOFF2_SIGNATURE.decode())
                            )
    return problems


def check_font_licenses(root):
    """Each family's folder under fonts/ holds a LICENSE with the text of the SIL Open Font License 1.1."""
    problems = []
    if not os.path.isdir(os.path.join(root, FONTS)):
        return problems
    for name in sorted(os.listdir(os.path.join(root, FONTS))):
        folder = FONTS + name
        if name.startswith(".") or not os.path.isdir(os.path.join(root, folder)):
            continue
        license_file = os.path.join(root, folder, "LICENSE")
        if not os.path.isfile(license_file):
            problems.append("fonts: %s has no LICENSE beside its fonts" % folder)
            continue
        with open(license_file, encoding="utf-8", errors="replace") as f:
            if OFL not in " ".join(f.read().split()).lower():
                problems.append("fonts: %s/LICENSE is not the SIL Open Font License 1.1" % folder)
    return problems


def check_font_stacks(sheets, pages):
    """--font-text names system fonts after Inter and ends in sans-serif, and --font-mono names system fonts after
    JetBrains Mono and ends in monospace, wherever a stylesheet declares them. A tree with no page needs neither."""
    problems = []
    for family, name, generic in FONT_STACKS:
        declared = [
            (rel, value)
            for rel, text in sheets.items()
            for value in re.findall(r"%s\s*:\s*([^;}]+)" % re.escape(name), text)
        ]
        if not declared and pages:
            problems.append("fonts: no stylesheet declares %s, the stack of %s" % (name, family))
        for rel, value in declared:
            fonts = [unquote_css(font) for font in split_list(value)]
            stack = "%s: %s (%s)" % (rel, name, clip(", ".join(fonts)))
            if family not in fonts:
                problems.append("fonts: %s does not name %s" % (stack, family))
            elif fonts[-1] != generic:
                problems.append("fonts: %s does not end in %s" % (stack, generic))
            elif len(fonts) - fonts.index(family) < 3:
                problems.append("fonts: %s names no system font between %s and %s" % (stack, family, generic))
    return problems


def blank(match):
    """The text of MATCH as spaces, its newlines kept, so that offsets and lines stay where they were."""
    return re.sub(r"[^\n]", " ", match.group(0))


def declarations(css, inline=False):
    """The declarations of a stylesheet's rules, or, INLINE, of a style attribute: the text read, comments, strings,
    and url()s blanked out, and (offset of the value in it, property, value, the rule's selector) for each. Only a rule
    that holds no other rule is read, so an at-rule's condition is no value."""
    text = CSS_STRING.sub(blank, CSS_COMMENT.sub(blank, css))
    bodies = [(0, text, "")] if inline else []
    opened = []  # [offset of a {, whether a rule opened inside it]
    for brace in re.finditer(r"[{}]", "" if inline else text):
        if brace.group() == "{":
            if opened:
                opened[-1][1] = True
            opened.append([brace.start(), False])
        elif opened:
            start, nested = opened.pop()
            if not nested:
                selector = text[max(text.rfind(c, 0, start) for c in "{};") + 1 : start].strip()
                bodies.append((start + 1, text[start + 1 : brace.start()], selector))
    found = []
    for offset, body, selector in bodies:
        for declaration in CSS_DECLARATION.finditer(body):
            found.append((offset + declaration.start(2), declaration.group(1).lower(), declaration.group(2), selector))
    return text, found


def rgb_of(color):
    """The red, green, and blue of a color as CSS writes it, its opacity aside, or None when it is none this reads."""
    color = color.strip().lower()
    color = NAMED_COLORS.get(color, color)
    if color.startswith("#"):
        digits = color[1:]
        if len(digits) in (3, 4):
            digits = "".join(digit * 2 for digit in digits)
        if len(digits) not in (6, 8) or re.search(r"[^0-9a-f]", digits):
            return None
        return tuple(int(digits[i : i + 2], 16) for i in (0, 2, 4))
    function = re.match(r"(rgba?|hsla?)\((.*)\)$", color, re.S)
    if not function:
        return None
    parts = function.group(2).replace(",", " ").replace("/", " ").split()
    if len(parts) < 3:
        return None
    try:
        if function.group(1).startswith("rgb"):
            return tuple(round(float(p[:-1]) * 2.55) if p.endswith("%") else round(float(p)) for p in parts[:3])
        hue = re.match(r"(-?[\d.]+)(deg|grad|rad|turn)?$", parts[0])
        if not hue:
            return None
        turns = {"grad": 400.0, "rad": 6.283185307179586, "turn": 1.0}.get(hue.group(2), 360.0)
        saturation, lightness = (float(p.rstrip("%")) / 100 for p in parts[1:3])
        rgb = colorsys.hls_to_rgb((float(hue.group(1)) / turns) % 1, lightness, saturation)
        return tuple(round(channel * 255) for channel in rgb)
    except ValueError:
        return None


def colors_in(css, inline=False):
    """(line, the color as written, its red, green, and blue or None) for each color the declarations of CSS write,
    the first line of CSS being line 1."""
    text, found = declarations(css, inline)
    colors = []
    for offset, _, value, _ in found:
        for match in CSS_COLOR.finditer(value):
            written = match.group(0)
            if match.group("word") is not None and written.lower() not in NAMED_COLORS:
                continue
            colors.append((text.count("\n", 0, offset + match.start()) + 1, written, rgb_of(written)))
    return colors


def placeholder_colors(root):
    """The placeholders' colors: the value of each custom property the :root block of PLACEHOLDERS declares as a color.
    A tree with no such file has none."""
    path = os.path.join(root, PLACEHOLDERS)
    if not os.path.isfile(path):
        return set()
    with open(path, encoding="utf-8", errors="replace") as f:
        _, found = declarations(f.read())
    colors = set()
    for _, name, value, selector in found:
        rgb = rgb_of(value)
        if selector == ":root" and name.startswith("--") and rgb is not None:
            colors.add(rgb)
    return colors


def check_colors(root, pages):
    """Every color of the styles — the stylesheets under styles/, and the pages' <style> elements and style
    attributes — is one of the logo's colors or a placeholder, at any opacity. A placeholder used through its custom
    property is a var(), no color; one written as its value passes as that value does."""
    allowed = set(rgb_of(color) for color in LOGO_COLORS) | placeholder_colors(root)
    sources = []  # (file, the line its CSS starts on, the CSS, whether it is a style attribute)
    for rel in site_files(root, skip_hidden=True):
        if rel.startswith(STYLES + "/") and rel.endswith(".css"):
            with open(os.path.join(root, rel), encoding="utf-8", errors="replace") as f:
                sources.append((rel, 1, f.read(), False))
    for rel, page in pages.items():
        sources += [(rel, line, css, False) for line, css in page.style_elements]
        sources += [(rel, line, css, True) for line, css in page.style_attributes]
    problems = []
    for rel, first, css, inline in sources:
        for line, written, rgb in colors_in(css, inline):
            if rgb not in allowed:
                problems.append(
                    "colors: %s:%d: %s is neither one of the logo's colors nor a placeholder of %s's :root block"
                    % (rel, first + line - 1, written, PLACEHOLDERS)
                )
    return problems


def main(argv):
    args = argv[1:]
    published = PUBLISHED
    if args[:1] == ["--languages"] and len(args) >= 2:
        published = tuple(args[1].split(","))
        args = args[2:]
    known = [language for language, _ in LANGUAGES]
    if len(args) > 1 or "en-US" not in published or any(language not in known for language in published):
        print("usage: check-site.py [--languages en-US,pt-BR,es-ES] [ROOT]", file=sys.stderr)
        return 2
    root = args[0] if args else "site"
    if not os.path.isdir(root):
        print("check-site: %s is not a directory" % root, file=sys.stderr)
        return 2
    pages = OrderedDict(
        (rel, read_page(root, rel)) for rel in site_files(root, skip_hidden=True) if rel.endswith(".html")
    )
    site_pages = list(pages)
    problems = check_unpublished(pages, published)
    problems += check_declared_languages(pages, published)
    problems += check_paths(pages)
    problems += check_parity(pages, published)
    problems += check_shared_blocks(root, pages, published)
    site = OrderedDict((rel, pages[rel]) for rel in site_pages)
    problems += check_text_languages(site)
    problems += check_links(root, pages)
    media_problems, media_count, media_total = check_media(root)
    problems += media_problems
    problems += check_posters(root, site)
    problems += check_metadata(root, site)
    problems += check_landing(site)
    problems += check_privacy(site, published)
    problems += check_support(site, published)
    problems += check_guide(site)
    problems += check_guide_sections(site)
    problems += check_reference(site)
    problems += check_not_found(root, site)
    sheets = stylesheets(root)
    problems += check_font_faces(root, sheets)
    problems += check_font_licenses(root)
    problems += check_font_stacks(sheets, site)
    problems += check_colors(root, site)
    for problem in problems:
        print("check-site: " + problem, file=sys.stderr)
    if problems:
        print("check-site: %d problems" % len(problems), file=sys.stderr)
        return 1
    print(
        "check-site: ok: %d pages, %d media files of %s bytes"
        % (len(site_pages), media_count, format(media_total, ","))
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

#!/usr/bin/env python3
"""Checks the site's files as committed, with no build step: that no page sits under a language the site does not
publish, that each page declares the language of the prefix it sits under on its root element and marks no element
with a language the site does not publish, the parity of the languages it does, the header and footer every page of
one language shares, the internal links and #anchors, the media budget, the metadata search engines and link previews
read: each page's canonical address, description, and Open Graph tags, the sitemap that lists the pages, and the
robots.txt that points to it, the landing page: its primary call to action leads to harmflow-app on GitHub and comes
before the community edition's link to the build instructions, and the page says that HarmFlow is coming to the Mac
App Store and links to no store page yet, and what two pages of each published language must say: the privacy
policy's five parts, each with a heading and text, and its naming of Google Analytics; the support page's link to
harmflow-app's issues, and no e-mail address on it. It names each problem it finds on stderr, one per line, and exits
1 when it finds any. The Checks workflow (.github/workflows/checks.yml) runs it on the checkout, and check-site-test.py
proves each check on a tree of its own that breaks it.

Usage: check-site.py [--languages en-US,pt-BR,es-ES] [ROOT]

ROOT is the folder GitHub Pages serves, site/ by default, so site/privacy/index.html is /privacy/. --languages names
the languages the site publishes, en-US only by default: the site is in English for now, and its translations come
back later under the prefixes LANGUAGES keeps for them.

The standard library only, and Python 3.9, so it runs on a Mac's own python3 as it does in CI.
"""

import os
import posixpath
import re
import sys
from collections import OrderedDict
from html.parser import HTMLParser
from urllib.parse import unquote, urljoin, urlsplit

# en-US at the root, pt-BR under /pt-br/, es-ES under /es-es/, with the same English slugs in each.
LANGUAGES = (("en-US", ""), ("pt-BR", "pt-br/"), ("es-ES", "es-es/"))

# The languages the site publishes unless --languages names others. A page under another language's prefix fails.
PUBLISHED = ("en-US",)

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

# Images, recordings, and sound, wherever they are in the tree. MB is 1,000,000 bytes, the stricter reading.
MEDIA_EXTENSIONS = (
    ".apng", ".avif", ".bmp", ".gif", ".heic", ".ico", ".jpeg", ".jpg", ".png", ".svg", ".tif", ".tiff", ".webp",
    ".avi", ".m4v", ".mkv", ".mov", ".mp4", ".mpeg", ".mpg", ".ogv", ".webm",
    ".aac", ".flac", ".m4a", ".mp3", ".oga", ".ogg", ".opus", ".wav",
)
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

# The privacy policy's parts, by the id of each one's heading, and the support page, in every published language.
PRIVACY = "privacy/index.html"
PRIVACY_PARTS = (
    ("app", "the HarmFlow app"),
    ("website", "this website"),
    ("analytics", "analytics"),
    ("google", "how Google processes the data"),
    ("withdraw", "withdrawing consent"),
)
SUPPORT = "support/index.html"

# Where the support page leads for defects and requests: this address, or one under it.
ISSUES = "https://github.com/harmflow/harmflow-app/issues"

# A plain e-mail address, name@domain.tld, in a page's visible text.
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")

HEADINGS = ("h1", "h2", "h3", "h4", "h5", "h6")

# Elements with no end tag, which never hold another, and the ones whose text no visitor reads.
VOID = (
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr",
)
HIDDEN = ("head", "script", "style", "template")


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
    """One HTML file: the ids its #anchors may name, the references it makes, its header's and footer's tokens, its
    visible text, and the outline its headings give that text."""

    def __init__(self, rel):
        super().__init__(convert_charrefs=True)
        self.rel = rel
        self.url = url_of(rel)
        self.ids = set()
        self.links = []  # (line, reference)
        self.raw_blocks = {}  # "header" or "footer": [token], each token a tag or a text
        self.canonical = None
        self.description = None
        self.open_graph = {}  # "og:title": its content
        self.anchors = []  # (line, href, is a primary call to action), each a element with an href, in the page's order
        self.hrefs = []  # (line, href), every href of the page, the head's included
        self.body_text = []  # the text of the body, what the visitor reads
        self._in_body = False
        self.declared = None  # the lang of the root element, "" when it has none
        self.marked = []  # (line, lang) of every other element with a lang
        self.text = []  # the visible text, a run of words per piece
        # In document order: ("heading", level, id, depth) where depth is the open elements' count around it,
        # ("text",) for visible text outside any heading, and ("end", depth) when an element closes, depth after.
        self.outline = []
        self._open = []  # the open elements, outermost first
        self._sectioning = 0
        self._capture = None
        self._depth = 0
        self._tokens = []

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
        if named.get("href") is not None:
            self.hrefs.append((line, named["href"]))
            if tag == "a":
                self.anchors.append((line, named["href"].strip(), "cta" in (named.get("class") or "").split()))
        if tag == "html" and self.declared is None:
            self.declared = (named.get("lang") or "").strip()
        elif named.get("lang") is not None:
            self.marked.append((line, named["lang"].strip()))
        for name, value in attrs:
            if value is None:
                continue
            if name == "id" or (tag == "a" and name == "name"):
                self.ids.add(value)
            if name in LINK_ATTRIBUTES.get(tag, ()):
                for ref in references(name, value):
                    self.links.append((line, ref))
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
        if tag in SECTIONING and self._sectioning:
            self._sectioning -= 1
        if self._capture:
            self._tokens.append(("end", tag, None))
            if tag == self._capture:
                self._depth -= 1
                if self._depth == 0:
                    self.raw_blocks[self._capture] = self._tokens
                    self._capture = None

    def handle_data(self, data):
        text = " ".join(data.split())
        if self._capture and text:
            self._tokens.append(("text", text, None))
        if self._in_body and text:
            self.body_text.append(text)
        if text and not any(tag in HIDDEN for tag in self._open):
            self.text.append(text)
            if not any(tag in HEADINGS for tag in self._open):
                self.outline.append(("text",))


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
        for line, ref in page.links:
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
    the page's body says HarmFlow is coming to the Mac App Store; and no href, the header's and footer's included, leads
    to the Mac App Store, where HarmFlow has no page yet. A tree with no landing page has none of this to check."""
    page = pages.get(LANDING)
    if page is None:
        return []
    problems = []
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


def published_pages(pages, published, slug):
    """The page at SLUG in each published language the tree holds."""
    return [rel for rel in pages if language_of(rel)[1] == slug and language_of(rel)[0] in published]


def check_privacy(pages, published):
    """Each published language's privacy policy has a heading for each of its five parts, by the part's id, with text
    after it, and names Google Analytics. A tree with no privacy policy has nothing to check."""
    problems = []
    for rel in published_pages(pages, published, PRIVACY):
        page = pages[rel]
        for part_id, part in PRIVACY_PARTS:
            has_text = part_has_text(page, part_id)
            if has_text is None:
                problems.append("privacy: %s has no heading with the id %s, for its part on %s" % (rel, part_id, part))
            elif not has_text:
                problems.append(
                    "privacy: %s: its part on %s (#%s) has no text after its heading" % (rel, part, part_id)
                )
        if "Google Analytics" not in " ".join(page.text):
            problems.append("privacy: %s does not name Google Analytics" % rel)
    return problems


def check_support(pages, published):
    """Each published language's support page links to harmflow-app's issues, or to an address under them, and gives no
    e-mail address, by a mailto: link or in its text. Only the support page is read for an address; a tree with no
    support page has nothing to check."""
    problems = []
    for rel in published_pages(pages, published, SUPPORT):
        page = pages[rel]
        hrefs = [href for _, href, _ in page.anchors]
        if not any(href == ISSUES or href.startswith((ISSUES + "/", ISSUES + "?", ISSUES + "#")) for href in hrefs):
            problems.append("support: %s has no link to %s" % (rel, ISSUES))
        addresses = OrderedDict()
        for href in hrefs:
            if href.lower().startswith("mailto:"):
                addresses.setdefault(unquote(href[len("mailto:") :].split("?")[0]) or href, None)
        for address in EMAIL.findall(" ".join(page.text)):
            addresses.setdefault(address, None)
        for address in addresses:
            problems.append("support: %s gives the e-mail address %s; the support page gives none" % (rel, address))
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
    problems += check_parity(pages, published)
    problems += check_shared_blocks(root, pages, published)
    site = OrderedDict((rel, pages[rel]) for rel in site_pages)
    problems += check_links(root, pages)
    media_problems, media_count, media_total = check_media(root)
    problems += media_problems
    problems += check_metadata(root, site)
    problems += check_landing(site)
    problems += check_privacy(site, published)
    problems += check_support(site, published)
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

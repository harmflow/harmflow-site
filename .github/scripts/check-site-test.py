#!/usr/bin/env python3
"""Tests of check-site.py: a site of its own that passes every check, and, for each check, the same site with one
thing broken, which must fail and name what broke. Every tree is built here, in a temporary directory, never
committed: a committed fixture would break the checks of the repository itself. The Checks workflow
(.github/workflows/checks.yml) runs it.

Usage: check-site-test.py [unittest options]
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "check-site.py")
SITE = os.path.join(os.path.dirname(os.path.dirname(HERE)), "site")

PREFIXES = (("en-US", ""), ("pt-BR", "pt-br/"), ("es-ES", "es-es/"))

# The fixture is published in the three languages, so the parity and the shared blocks of each stay proven while the
# site itself publishes en-US only, check-site.py's default.
ALL_LANGUAGES = ["--languages", "en-US,pt-BR,es-ES"]
SLUGS = (
    "index.html",
    "docs/guide/index.html",
    "docs/guide/install/index.html",
    "docs/guide/repository-access/index.html",
    "docs/guide/tasks/index.html",
    "docs/guide/executions/index.html",
    "docs/reference/index.html",
    "showroom/index.html",
    "privacy/index.html",
    "support/index.html",
)
# The sections the footer every page shares links to, as the site's does: each one's path and its link's text.
SECTIONS = (
    ("docs/guide/", "Guide"),
    ("docs/reference/", "Reference"),
    ("showroom/", "Showroom"),
    ("privacy/", "Privacy"),
    ("support/#contact", "Support"),
)
MB = 1000 * 1000

# What the privacy policy and the support page of every language say, which their checks read: the policy's six parts,
# each a heading by its id with text after it, the app's part saying it sends nothing and keeps what it keeps on the
# Mac, the retention part its period and that a return visit does not extend it, and the withdrawal part the footer's
# link by its label; and the support page's link to an address under harmflow-app's issues, and that they are not
# support.
PRIVACY_PARTS = (
    ("app", "the HarmFlow app"),
    ("website", "this website"),
    ("analytics", "analytics"),
    ("google", "how Google processes the data"),
    ("retention", "how long the data is kept"),
    ("withdraw", "withdrawing consent"),
)
APP_PART = "  <p>It sends nothing to HarmFlow, and what it keeps stays on your Mac.</p>\n"
RETENTION_PART = (
    "  <p>Google Analytics keeps the detailed data for two months, and does not extend that period when you come"
    " back.</p>\n"
)
WITHDRAW_PART = "  <p>Use the Analytics choice link in the footer of every page, which reopens the choice.</p>"
PRIVACY = (
    """<h2 id="app">The HarmFlow app</h2>
%s  <h2 id="website">This website</h2>
  <p>It sets no cookie of its own.</p>
  <h2 id="analytics">Analytics</h2>
  <p>It measures its visits with Google Analytics, once you accept.</p>
  <h3 id="google">How Google processes the data</h3>
  <p>Google receives each measured event.</p>
  <h3 id="retention">How long it is kept</h3>
%s  <h3 id="withdraw">Withdrawing your consent</h3>
%s"""
    % (APP_PART, RETENTION_PART, WITHDRAW_PART)
)
NOT_SUPPORT = "<p>The issues are not a support channel.</p>"
SUPPORT = (
    '<p><a href="https://github.com/harmflow/harmflow-app/issues/new/choose">Open an issue</a></p>\n  ' + NOT_SUPPORT
)

# The footer's link that reopens the analytics choice, which the policy's part on withdrawing names by its label.
CONSENT_LINK = '  <a href="/%sprivacy/#withdraw" data-consent-choice>Analytics choice</a>\n'

# The user guide, which its check reads in en-US: the index's main leads to the four parts in their order, with a link
# to another section between two of them, and each part's page has its title as its h1 and an introduction.
GUIDE_PARTS = (
    ("docs/guide/install/", "Installing HarmFlow"),
    ("docs/guide/repository-access/", "Granting access to repositories"),
    ("docs/guide/tasks/", "Creating tasks"),
    ("docs/guide/executions/", "Reading executions"),
)
GUIDE_LINKS = tuple('<li><a href="/%s">%s</a></li>' % part for part in GUIDE_PARTS)
GUIDE = "<ol>\n    %s\n  </ol>" % "\n    ".join(
    GUIDE_LINKS[:2] + ('<li><a href="/docs/reference/">The reference</a></li>',) + GUIDE_LINKS[2:]
)
INTRODUCTION = "<p>What this part of the guide covers.</p>"

# A section of the guide, one folder below the tasks part, which the guide's section cases add to the site as it is
# published: its page, the part's link to it, and the paragraph of text after its h1.
GUIDE_SECTION = "docs/guide/tasks/yaml-tab/index.html"
GUIDE_SECTION_LINK = '<ul><li><a href="/docs/guide/tasks/yaml-tab/">Editing a task as YAML</a></li></ul>'
GUIDE_SECTION_TEXT = "<p>What this section of the guide says.</p>"


def prefix_of(language):
    return dict(PREFIXES)[language]


def served(prefix, slug):
    """The path a page is served at: pt-br/privacy/index.html at /pt-br/privacy/."""
    return "/" + prefix + ("" if slug == "index.html" else slug[: -len("index.html")])


def header(language, slug):
    """The header every page of a language shares: its home, and the selector that leads to this page in the other
    two languages, which differs on every page."""
    selector = "".join(
        '    <a href="%s" hreflang="%s">%s</a>\n' % (served(prefix, slug), other, other)
        for other, prefix in PREFIXES
        if other != language
    )
    return '<header>\n  <a href="/%s">HarmFlow</a>\n  <nav>\n%s  </nav>\n</header>' % (prefix_of(language), selector)


def footer(language, sections=SECTIONS):
    prefix = prefix_of(language)
    links = "".join('  <a href="/%s%s">%s</a>\n' % (prefix, path, text) for path, text in sections)
    return "<footer>\n%s%s</footer>" % (links, CONSENT_LINK % prefix)


# What the landing page, the en-US index.html, must hold: the badge that says HarmFlow is coming to the Mac App Store,
# the lead that says whom it is for, a primary call to action to the app on GitHub, and after it the community
# edition's link to the build instructions.
BADGE = '<p class="badge">Coming to the Mac App Store</p>'
AUDIENCE = '<p class="lead">For developers on the Mac: HarmFlow runs Claude Code and Codex on a schedule.</p>'
CTA = '<a class="cta" href="https://github.com/harmflow/harmflow-app">Follow HarmFlow on GitHub</a>'
COMMUNITY = '<p>The community edition <a href="https://github.com/harmflow/harmflow-app#quick-start">builds</a>.</p>'
LANDING = "\n  ".join((BADGE, AUDIENCE, CTA, COMMUNITY))


def page(language, slug, header_html=None, footer_html=None, body="", landing=None):
    """A page of the fixture. The privacy policy holds its parts, the support page its link to the issues, the guide's
    index its links to the parts, and each part its introduction, after BODY; a part's h1 is its title. Every page but
    the support page has a mailto: link, which only the support page may not."""
    home = "./" if slug == "index.html" else "../" * slug.count("/")
    if landing is None:
        landing = LANDING if (language, slug) == ("en-US", "index.html") else ""
    parts = dict((path + "index.html", title) for path, title in GUIDE_PARTS)
    content = {"privacy/index.html": PRIVACY, "support/index.html": SUPPORT, "docs/guide/index.html": GUIDE}.get(
        slug, INTRODUCTION if slug in parts else ""
    )
    mail = "" if slug == "support/index.html" else ' <a href="mailto:support@example.com">Mail</a>'
    return """<!doctype html>
<html lang="%(language)s">
<head>
  <meta charset="utf-8">
  <title>A page</title>
  <meta name="description" content="A page of the fixture.">
  <link rel="canonical" href="https://harmflow.com%(served)s">
  <meta property="og:type" content="website">
  <meta property="og:site_name" content="HarmFlow">
  <meta property="og:title" content="A page">
  <meta property="og:description" content="A page of the fixture.">
  <meta property="og:url" content="https://harmflow.com%(served)s">
  <meta property="og:image" content="https://harmflow.com/og-image.png">
  <link rel="stylesheet" href="/styles/site.css">
</head>
<body>
%(header)s
<main>
  <h1 id="title">%(title)s</h1>
  <p><a href="#title">Title</a> <a href="#top">Top</a> <a href="%(home)s">Home</a></p>
  <p><a href="https://github.com/harmflow/harmflow-app">The app</a>%(mail)s</p>
  <img src="/showroom/poster.png" srcset="/showroom/poster.png 1x, https://harmflow.com/showroom/poster.png 2x" alt="">
  <h2 id="contact">Contact</h2>
  %(landing)s
  %(body)s
  %(content)s
</main>
%(footer)s
</body>
</html>
""" % {
        "language": language,
        "served": served(prefix_of(language), slug),
        "header": header_html if header_html is not None else header(language, slug),
        "home": home,
        "title": parts.get(slug, "A page"),
        "landing": landing,
        "mail": mail,
        "body": body,
        "content": content,
        "footer": footer_html if footer_html is not None else footer(language),
    }


NOT_FOUND = """<!doctype html>
<html lang="en-US">
<head><meta charset="utf-8"></head>
<body>
<header><a href="/">HarmFlow</a></header>
<main>
  <h1>Page not found</h1>
  <p><a href="/">Home</a></p>
  <p lang="pt-BR">Página não encontrada. <a href="/pt-br/">Início</a></p>
  <p lang="es-ES">Página no encontrada. <a href="/es-es/">Inicio</a></p>
</main>
</body>
</html>
"""

# The header of a page of the site in en-US only: no selector, since there is no other language to lead to.
EN_US_HEADER = '<header>\n  <a href="/">HarmFlow</a>\n</header>'

# The 404 page as the site publishes it in en-US only: its pt-BR and es-ES paragraphs taken out.
NOT_FOUND_EN_US = NOT_FOUND[: NOT_FOUND.index('  <p lang="pt-BR">')] + NOT_FOUND[NOT_FOUND.index("</main>") :]


# A paragraph of English beside a case's paragraph in another language, so that only that paragraph fails, not the
# whole main.
ENGLISH = "<p>This page tells you where to ask for help with the app, and how to report what you find in it.</p>"


def line_of(text, fragment):
    """The line of TEXT that holds FRAGMENT, counted from 1."""
    return text[: text.index(fragment)].count("\n") + 1


def sitemap(rels):
    """A sitemap that lists the pages RELS by their published address."""
    urls = "".join("  <url><loc>https://harmflow.com%s</loc></url>\n" % served("", rel) for rel in rels)
    head = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    return head + urls + "</urlset>\n"


ROBOTS = "User-agent: *\nAllow: /\n\nSitemap: https://harmflow.com/sitemap.xml\n"

# The fixture's styles: one WOFF2 file per family, named from the root and relative to the stylesheet; the two
# stacks, each with a system font before its generic family; and two placeholders in site.css's :root block, used
# through their custom properties.
STYLESHEET = """/* A comment with @font-face { src: url("https://example.com/x.ttf"); } in it, which no check reads. */
@font-face {
  font-family: "Inter";
  font-display: swap;
  src: url("/fonts/inter/inter.woff2") format("woff2");
}

@font-face {
  font-family: 'JetBrains Mono';
  src: url(../fonts/jetbrains-mono/jetbrains-mono.woff2) format('woff2');
}

/* The placeholders, until the palette is approved. */
:root {
  --bg: #0b0f1a;
  --text: #e6e8ee;
  --font-text: "Inter", system-ui, sans-serif;
  --font-mono: "JetBrains Mono", ui-monospace, Menlo, monospace;
}

body { margin: 0; background: var(--bg); color: var(--text); font-family: var(--font-text); }
"""

# Not really a font: the four bytes every WOFF2 file starts with, then text.
WOFF2 = "wOF2 not really a font\n"

FONT_LICENSE = """Copyright 2026 The Fixture Project Authors

This Font Software is licensed under the SIL Open Font License, Version 1.1.

-----------------------------------------------------------
SIL OPEN FONT LICENSE Version 1.1 - 26 February 2007
-----------------------------------------------------------
"""


class CheckSiteTest(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.mkdtemp(prefix="check-site-test.")
        self.addCleanup(shutil.rmtree, scratch)
        self.root = os.path.join(scratch, "site")
        for language, prefix in PREFIXES:
            for slug in SLUGS:
                self.write(prefix + slug, page(language, slug))
        self.write("404.html", NOT_FOUND)
        self.write("sitemap.xml", sitemap(prefix + slug for _, prefix in PREFIXES for slug in SLUGS))
        self.write("robots.txt", ROBOTS)
        self.write("og-image.png", "not really a png\n")
        self.write("styles/site.css", STYLESHEET)
        for family in ("inter", "jetbrains-mono"):
            self.write("fonts/%s/%s.woff2" % (family, family), WOFF2)
            self.write("fonts/%s/LICENSE" % family, FONT_LICENSE)
        self.write("showroom/poster.png", "not really a png\n")
        self.write("README.md", "Not a page.\n")

    def lay_out(self, slugs, sections):
        """The site with only the pages SLUGS in every language, each footer linking to SECTIONS, and a sitemap that
        lists those pages: a change that moves or removes a page together with its links and its sitemap entry."""
        for language, prefix in PREFIXES:
            for slug in SLUGS:
                if slug not in slugs:
                    os.remove(os.path.join(self.root, prefix + slug))
            for slug in slugs:
                self.write(prefix + slug, page(language, slug, footer_html=footer(language, sections)))
        self.write("sitemap.xml", sitemap(prefix + slug for _, prefix in PREFIXES for slug in slugs))

    def write(self, rel, text):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

    def en_us_only(self):
        """The site as it is published for now: en-US pages with no selector, and a 404 page in en-US."""
        for _, prefix in PREFIXES[1:]:
            shutil.rmtree(os.path.join(self.root, prefix))
        for slug in SLUGS:
            self.write(slug, page("en-US", slug, header_html=EN_US_HEADER))
        self.write("404.html", NOT_FOUND_EN_US)
        self.write("sitemap.xml", sitemap(SLUGS))

    def sparse(self, rel, size):
        """A file of SIZE bytes that takes no room on disk."""
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.truncate(size)

    def check(self, root=None, languages=ALL_LANGUAGES):
        result = subprocess.run(
            [sys.executable, SCRIPT] + languages + [root or self.root],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
        )
        return result.returncode, result.stdout, result.stderr

    def assertPasses(self, root=None, languages=ALL_LANGUAGES):
        rc, out, err = self.check(root, languages)
        self.assertEqual(rc, 0, err)
        self.assertIn("check-site: ok", out)

    def assertFails(self, *texts, languages=ALL_LANGUAGES):
        """The check exits 1, and its output holds each of TEXTS. It returns the output's problem lines."""
        rc, _, err = self.check(languages=languages)
        self.assertEqual(rc, 1, err)
        for text in texts:
            self.assertIn(text, err)
        return [line for line in err.splitlines() if not line.endswith(" problems")]

    def restyle(self, old, new):
        """The fixture's stylesheet with OLD replaced by NEW; OLD must be in it, so a case cannot pass unbroken."""
        self.assertIn(old, STYLESHEET)
        self.write("styles/site.css", STYLESHEET.replace(old, new, 1))

    # The site every case breaks passes: three languages, a selector whose links differ on every page, relative,
    # root, and harmflow.com links, anchors, a srcset, and the root 404 page in all three languages.
    def test_the_site_passes(self):
        self.assertPasses()

    def test_a_tree_with_no_page_passes(self):
        empty = os.path.join(self.root, "..", "empty")
        os.makedirs(empty)
        self.assertPasses(empty, languages=[])

    # The repository's own site/, the folder GitHub Pages serves, not the repository's root, with the default languages.
    def test_the_published_site_passes(self):
        self.assertPasses(SITE, languages=[])

    # Published languages.

    def test_the_site_in_en_us_only_passes_by_default(self):
        self.en_us_only()
        self.assertPasses(languages=[])

    def test_a_page_in_a_language_not_published_fails_naming_it(self):
        self.write("404.html", NOT_FOUND_EN_US)
        lines = self.assertFails(
            "unpublished: pt-br/privacy/index.html is a pt-BR page, and the site publishes only en-US",
            "unpublished: es-es/index.html is a es-ES page",
            languages=[],
        )
        self.assertEqual(len([line for line in lines if "unpublished:" in line]), 2 * len(SLUGS), lines)
        self.assertEqual([line for line in lines if "parity:" in line], [], lines)
        # Each of those pages declares its own prefix's language, so only its prefix fails it.
        self.assertEqual([line for line in lines if "languages:" in line], [], lines)

    # Declared languages.

    def test_a_page_that_declares_no_language_fails_naming_it(self):
        self.write("privacy/index.html", page("en-US", "privacy/index.html").replace('<html lang="en-US">', "<html>"))
        self.write("es-es/index.html", page("es-ES", "index.html").replace('<html lang="es-ES">', '<html lang="">'))
        lines = self.assertFails(
            "languages: privacy/index.html declares no language on its root element; it is en-US",
            "languages: es-es/index.html declares no language on its root element; it is es-ES",
        )
        self.assertEqual(len([line for line in lines if "languages:" in line]), 2, lines)

    def test_a_page_that_declares_another_language_than_its_prefix_fails_naming_it(self):
        self.write("index.html", page("en-US", "index.html").replace('<html lang="en-US">', '<html lang="pt-BR">'))
        text = page("pt-BR", "support/index.html").replace('<html lang="pt-BR">', '<html lang="en-US">')
        self.write("pt-br/support/index.html", text)
        lines = self.assertFails(
            "languages: index.html declares pt-BR on its root element, not en-US",
            "languages: pt-br/support/index.html declares en-US on its root element, not pt-BR",
        )
        self.assertEqual(len([line for line in lines if "languages:" in line]), 2, lines)

    def test_a_root_page_that_declares_another_language_fails_by_default(self):
        self.en_us_only()
        text = page("en-US", "support/index.html", header_html=EN_US_HEADER)
        self.write("support/index.html", text.replace('<html lang="en-US">', '<html lang="es-ES">'))
        lines = self.assertFails(
            "languages: support/index.html declares es-ES on its root element, not en-US", languages=[]
        )
        self.assertEqual(lines, [lines[0]], lines)

    def test_a_declared_language_in_another_case_passes(self):
        self.en_us_only()
        self.write("404.html", NOT_FOUND_EN_US.replace('<html lang="en-US">', '<html lang="en-us">'))
        text = page("en-US", "index.html", header_html=EN_US_HEADER)
        self.write("index.html", text.replace('<html lang="en-US">', '<html lang="EN-us">'))
        self.assertPasses(languages=[])

    def test_the_root_404_page_must_declare_en_us(self):
        self.write("404.html", NOT_FOUND.replace('<html lang="en-US">', '<html lang="pt-BR">'))
        lines = self.assertFails("languages: 404.html declares pt-BR on its root element, not en-US")
        self.assertEqual(len([line for line in lines if "languages:" in line]), 1, lines)

    def test_an_element_marked_with_a_language_not_published_fails_naming_its_line(self):
        self.en_us_only()
        body = '<p lang="pt-br">Suporte</p>'
        text = page("en-US", "support/index.html", header_html=EN_US_HEADER, body=body)
        self.write("support/index.html", text)
        lines = self.assertFails(
            "languages: support/index.html:%d: an element is marked pt-br, a language the site does not publish"
            % line_of(text, body),
            languages=[],
        )
        self.assertEqual(lines, [lines[0]], lines)

    def test_the_404_page_with_its_translations_fails_by_default(self):
        self.en_us_only()
        self.write("404.html", NOT_FOUND)
        lines = self.assertFails(
            "languages: 404.html:%d: an element is marked pt-BR" % line_of(NOT_FOUND, '<p lang="pt-BR">'),
            "languages: 404.html:%d: an element is marked es-ES" % line_of(NOT_FOUND, '<p lang="es-ES">'),
            languages=[],
        )
        self.assertEqual(len([line for line in lines if "languages:" in line]), 2, lines)

    def test_an_element_marked_with_a_published_or_unknown_language_passes(self):
        self.en_us_only()
        body = '<p lang="en">Support</p> <span lang="fr-FR">Assistance</span> <span lang="">?</span>'
        self.write("support/index.html", page("en-US", "support/index.html", header_html=EN_US_HEADER, body=body))
        self.assertPasses(languages=[])

    # Text languages.

    def test_a_paragraph_in_portuguese_fails_naming_its_line(self):
        self.en_us_only()
        body = "<p>Esta tarefa não roda quando você fecha o app, e também não guarda o seu histórico.</p>"
        text = page("en-US", "support/index.html", header_html=EN_US_HEADER, body=ENGLISH + "\n  " + body)
        self.write("support/index.html", text)
        lines = self.assertFails(
            "text language: support/index.html:%d: a paragraph reads as Portuguese" % line_of(text, body),
            languages=[],
        )
        self.assertEqual(lines, [lines[0]], lines)

    def test_a_paragraph_in_spanish_fails_naming_its_line(self):
        self.en_us_only()
        body = "<ul>\n  <li>La tarea se guarda en el archivo y usted puede editarla después.</li>\n</ul>"
        text = page("en-US", "docs/reference/index.html", header_html=EN_US_HEADER, body=body + "\n  " + ENGLISH)
        self.write("docs/reference/index.html", text)
        lines = self.assertFails(
            "text language: docs/reference/index.html:%d: a paragraph reads as Spanish" % line_of(text, "<li>La"),
            languages=[],
        )
        self.assertEqual(lines, [lines[0]], lines)

    # Each paragraph is too short to judge, so only the main as a whole reads as Portuguese, the page's shared English
    # header and footer kept around it.
    def test_a_main_wholly_in_portuguese_fails_naming_the_page(self):
        self.en_us_only()
        main = """<main>
  <h1>Vitrine</h1>
  <p>Você encontra aqui as gravações.</p>
  <p>Também pode abrir uma delas inteira.</p>
  <p>Isso leva só um minuto.</p>
</main>"""
        text = page("en-US", "showroom/index.html", header_html=EN_US_HEADER)
        text = text[: text.index("<main>")] + main + text[text.index("</main>") + len("</main>") :]
        self.write("showroom/index.html", text)
        lines = self.assertFails("text language: showroom/index.html: its main reads as Portuguese", languages=[])
        self.assertEqual(lines, [lines[0]], lines)

    # Code, product names, a language named in its own words, a borrowed word, and a short body pass.
    def test_an_english_page_with_code_names_and_a_short_body_passes(self):
        self.en_us_only()
        body = """<p>Run <code>harmflow task add --name "não use isso, pero también"</code> in the terminal.</p>
  <pre>echo "Esta tarefa não roda quando você fecha o app, e também não guarda o seu histórico."</pre>
  <p>Press <kbd>Cmd</kbd>, then type <kbd>los ángeles con las otras</kbd> to search.</p>
  <p>The site is in English; Português and Español come back later, as pt-BR and es-ES, under their own paths.</p>
  <p>Claude Code and Codex run your tasks on the Mac, with a fiesta of logs if you ask for them.</p>
  <p>Não, também.</p>"""
        self.write("support/index.html", page("en-US", "support/index.html", header_html=EN_US_HEADER, body=body))
        self.write("docs/reference/index.html", page("en-US", "docs/reference/index.html", header_html=EN_US_HEADER))
        self.assertPasses(languages=[])

    # A page that declares Portuguese or Spanish is its own language's: only an en-US page is judged.
    def test_a_page_that_declares_another_language_in_that_language_passes(self):
        body = "<p>Esta tarefa não roda quando você fecha o app, e também não guarda o seu histórico.</p>"
        self.write("pt-br/support/index.html", page("pt-BR", "support/index.html", body=body))
        self.assertPasses()

    def test_an_unknown_language_is_a_usage_error(self):
        rc, _, err = self.check(languages=["--languages", "en-US,fr-FR"])
        self.assertEqual(rc, 2, err)
        self.assertIn("usage:", err)

    # Paths.

    # Every other check passes a section deleted with its links and its sitemap entry: only this one names it.
    def test_a_section_removed_with_its_links_fails_naming_it(self):
        slugs = tuple(slug for slug in SLUGS if slug != "showroom/index.html")
        self.lay_out(slugs, tuple(section for section in SECTIONS if section[0] != "showroom/"))
        lines = self.assertFails("paths: /showroom/ has no page: showroom/index.html is missing")
        self.assertEqual(lines, ["check-site: paths: /showroom/ has no page: showroom/index.html is missing"])

    # Every other check passes a section moved, in every language, with its links and its sitemap entry.
    def test_a_section_moved_to_another_slug_fails_naming_it(self):
        slugs = tuple("docs/guia/index.html" if slug == "docs/guide/index.html" else slug for slug in SLUGS)
        sections = tuple(("docs/guia/", text) if path == "docs/guide/" else (path, text) for path, text in SECTIONS)
        self.lay_out(slugs, sections)
        lines = self.assertFails("paths: /docs/guide/ has no page: docs/guide/index.html is missing")
        self.assertEqual(lines, ["check-site: paths: /docs/guide/ has no page: docs/guide/index.html is missing"])

    def test_each_missing_path_is_one_problem_line(self):
        self.lay_out(("privacy/index.html",), (("privacy/", "Privacy"),))
        missing = [
            "paths: / has no page: index.html is missing",
            "paths: /docs/guide/ has no page: docs/guide/index.html is missing",
            "paths: /docs/reference/ has no page: docs/reference/index.html is missing",
            "paths: /showroom/ has no page: showroom/index.html is missing",
            "paths: /support/ has no page: support/index.html is missing",
        ]
        lines = self.assertFails(*missing)
        self.assertEqual([line for line in lines if "paths:" in line], ["check-site: " + text for text in missing])

    def test_a_page_below_a_required_path_does_not_stand_for_it(self):
        slugs = tuple("docs/guide/install/index.html" if slug == "docs/guide/index.html" else slug for slug in SLUGS)
        sections = tuple(
            ("docs/guide/install/", text) if path == "docs/guide/" else (path, text) for path, text in SECTIONS
        )
        self.lay_out(slugs, sections)
        lines = self.assertFails("paths: /docs/guide/ has no page: docs/guide/index.html is missing")
        self.assertEqual(lines, ["check-site: paths: /docs/guide/ has no page: docs/guide/index.html is missing"])

    # The paths are read at the root, in en-US: a translation at the same slug does not stand for one.
    def test_a_translation_does_not_stand_for_an_en_us_path(self):
        os.remove(os.path.join(self.root, "privacy/index.html"))
        lines = self.assertFails("paths: /privacy/ has no page: privacy/index.html is missing")
        self.assertEqual(len([line for line in lines if "paths:" in line]), 1, lines)

    # Parity.

    def test_an_en_us_page_with_no_pt_br_version_fails(self):
        os.remove(os.path.join(self.root, "pt-br/privacy/index.html"))
        lines = self.assertFails("parity: pt-br/privacy/index.html is missing")
        self.assertEqual(len([line for line in lines if "parity:" in line]), 1, lines)

    def test_an_en_us_page_with_no_es_es_version_fails(self):
        self.write("about/index.html", page("en-US", "about/index.html"))
        self.write("pt-br/about/index.html", page("pt-BR", "about/index.html"))
        self.assertFails("parity: es-es/about/index.html is missing")

    def test_a_translated_page_with_no_en_us_version_fails(self):
        self.write("pt-br/about/index.html", page("pt-BR", "about/index.html"))
        self.write("es-es/about/index.html", page("es-ES", "about/index.html"))
        self.assertFails("parity: about/index.html is missing")

    def test_a_translated_slug_fails(self):
        os.rename(os.path.join(self.root, "pt-br/privacy"), os.path.join(self.root, "pt-br/privacidade"))
        self.assertFails("parity: pt-br/privacy/index.html is missing", "parity: privacidade/index.html is missing")

    def test_only_the_root_404_page_needs_no_versions(self):
        self.write("pt-br/404.html", NOT_FOUND)
        self.assertFails("parity: es-es/404.html is missing")

    # Shared blocks.

    def test_one_pt_br_footer_that_differs_fails_naming_its_page(self):
        changed = footer("pt-BR").replace("Privacy", "Privacidade")
        self.write("pt-br/support/index.html", page("pt-BR", "support/index.html", footer_html=changed))
        lines = self.assertFails("shared blocks: pt-br/support/index.html: its footer differs")
        self.assertEqual([line for line in lines if "shared blocks:" in line], [lines[0]], lines)

    def test_one_en_us_header_that_differs_fails_naming_its_page(self):
        changed = header("en-US", "privacy/index.html").replace("HarmFlow", "Harmflow")
        self.write("privacy/index.html", page("en-US", "privacy/index.html", header_html=changed))
        self.assertFails(
            "shared blocks: privacy/index.html: its header differs", "Harmflow where the others have HarmFlow"
        )

    def test_a_page_with_no_footer_fails(self):
        self.write("es-es/index.html", page("es-ES", "index.html", footer_html=""))
        self.assertFails("shared blocks: es-es/index.html: its footer differs")

    # The site as it is published for now, checked with the default languages.
    def test_one_en_us_footer_that_differs_fails_naming_its_page(self):
        self.en_us_only()
        changed = footer("en-US").replace("Privacy", "Privacy policy")
        self.write("support/index.html", page("en-US", "support/index.html", EN_US_HEADER, footer_html=changed))
        lines = self.assertFails("shared blocks: support/index.html: its footer differs", languages=[])
        blocks = [line for line in lines if "shared blocks:" in line]
        self.assertEqual(len(blocks), 1, lines)
        self.assertIn("shared blocks: support/index.html: its footer differs", blocks[0])

    def test_an_en_us_page_with_no_footer_fails(self):
        self.en_us_only()
        self.write("privacy/index.html", page("en-US", "privacy/index.html", EN_US_HEADER, footer_html=""))
        lines = self.assertFails("shared blocks: privacy/index.html: its footer differs", languages=[])
        blocks = [line for line in lines if "shared blocks:" in line]
        self.assertEqual(len(blocks), 1, lines)
        self.assertIn("shared blocks: privacy/index.html: its footer differs", blocks[0])

    def test_a_selector_that_leads_to_another_page_fails(self):
        wrong = header("es-ES", "privacy/index.html").replace("/pt-br/privacy/", "/pt-br/support/")
        self.write("es-es/privacy/index.html", page("es-ES", "privacy/index.html", header_html=wrong))
        self.assertFails("shared blocks: es-es/privacy/index.html: its header differs")

    def test_two_versions_with_no_majority_name_every_page(self):
        for slug in SLUGS[len(SLUGS) // 2 :]:
            self.write(slug, page("en-US", slug, footer_html="<footer>Another footer</footer>"))
        lines = self.assertFails("no version is shared by most")
        named = sorted(line.split(": ")[2] for line in lines if "shared blocks:" in line)
        self.assertEqual(named, sorted(SLUGS))

    def test_the_same_markup_with_other_whitespace_passes(self):
        reflowed = " ".join(header("pt-BR", "privacy/index.html").split())
        self.write("pt-br/privacy/index.html", page("pt-BR", "privacy/index.html", header_html=reflowed))
        self.assertPasses()

    # Links.

    def test_a_broken_internal_link_fails(self):
        self.write("support/index.html", page("en-US", "support/index.html", body='<a href="/suport/">Support</a>'))
        self.assertFails("links: support/index.html:", "/suport/ leads to no file")

    def test_a_broken_relative_link_fails(self):
        self.write("pt-br/privacy/index.html", page("pt-BR", "privacy/index.html", body='<a href="../suporte/">x</a>'))
        self.assertFails("links: pt-br/privacy/index.html:", "../suporte/ leads to no file")

    def test_a_broken_harmflow_com_link_fails(self):
        body = '<link rel="alternate" hreflang="pt-BR" href="https://harmflow.com/pt-br/privacidade/">'
        self.write("privacy/index.html", page("en-US", "privacy/index.html", body=body))
        self.assertFails("https://harmflow.com/pt-br/privacidade/ leads to no file")

    def test_a_missing_image_fails(self):
        self.write("index.html", page("en-US", "index.html", body='<img src="/showroom/missing.png" alt="">'))
        self.assertFails("links: index.html:", "/showroom/missing.png leads to no file")

    def test_a_missing_srcset_candidate_fails(self):
        body = '<img src="/showroom/poster.png" srcset="/showroom/poster.png 1x, /showroom/poster@2x.png 2x" alt="">'
        self.write("index.html", page("en-US", "index.html", body=body))
        self.assertFails("/showroom/poster@2x.png leads to no file")

    def test_a_broken_anchor_on_the_same_page_fails(self):
        self.write("es-es/index.html", page("es-ES", "index.html", body='<a href="#contacto">x</a>'))
        self.assertFails("links: es-es/index.html:", "#contacto names no id of es-es/index.html")

    def test_a_broken_anchor_on_another_page_fails(self):
        self.write("index.html", page("en-US", "index.html", body='<a href="/privacy/#cookies">x</a>'))
        self.assertFails("/privacy/#cookies names no id of privacy/index.html")

    # Metadata.

    def test_a_page_with_no_canonical_address_fails_naming_it(self):
        text = page("en-US", "support/index.html").replace(
            '  <link rel="canonical" href="https://harmflow.com/support/">\n', ""
        )
        self.write("support/index.html", text)
        self.assertFails(
            "metadata: support/index.html declares no canonical address; it is https://harmflow.com/support/"
        )

    def test_a_canonical_address_of_another_page_fails(self):
        text = page("pt-BR", "privacy/index.html").replace(
            'rel="canonical" href="https://harmflow.com/pt-br/privacy/"',
            'rel="canonical" href="https://harmflow.com/"',
        )
        self.write("pt-br/privacy/index.html", text)
        self.assertFails("metadata: pt-br/privacy/index.html: its canonical address is https://harmflow.com/, not")

    def test_a_page_with_no_description_fails(self):
        text = page("en-US", "index.html").replace('  <meta name="description" content="A page of the fixture.">\n', "")
        self.write("index.html", text)
        self.assertFails("metadata: index.html has no description")

    def test_a_page_with_no_open_graph_tags_fails_naming_them(self):
        text = page("es-ES", "support/index.html")
        for name in ("og:title", "og:image"):
            text = "\n".join(line for line in text.split("\n") if 'property="%s"' % name not in line)
        self.write("es-es/support/index.html", text)
        self.assertFails("metadata: es-es/support/index.html has no og:title, og:image")

    def test_an_og_url_other_than_the_canonical_address_fails(self):
        text = page("en-US", "privacy/index.html").replace(
            'property="og:url" content="https://harmflow.com/privacy/"',
            'property="og:url" content="https://harmflow.com/"',
        )
        self.write("privacy/index.html", text)
        self.assertFails("metadata: privacy/index.html: its og:url is https://harmflow.com/, not")

    def test_an_og_image_on_another_host_or_missing_fails(self):
        text = page("en-US", "index.html").replace(
            "https://harmflow.com/og-image.png", "https://example.com/og-image.png"
        )
        self.write("index.html", text)
        os.remove(os.path.join(self.root, "og-image.png"))
        lines = self.assertFails("metadata: index.html: its og:image https://example.com/og-image.png is no image")
        # index.html names another host; every other page names an image the tree no longer holds.
        self.assertEqual(len([line for line in lines if "og:image" in line]), len(PREFIXES) * len(SLUGS), lines)

    def test_a_page_the_sitemap_does_not_list_fails(self):
        self.write("about/index.html", page("en-US", "about/index.html"))
        self.write("pt-br/about/index.html", page("pt-BR", "about/index.html"))
        self.write("es-es/about/index.html", page("es-ES", "about/index.html"))
        self.assertFails("metadata: sitemap.xml does not list https://harmflow.com/about/ (about/index.html)")

    def test_a_sitemap_entry_with_no_page_fails(self):
        pages = [prefix + slug for _, prefix in PREFIXES for slug in SLUGS]
        self.write("sitemap.xml", sitemap(pages + ["gone/index.html"]))
        self.assertFails("metadata: sitemap.xml lists https://harmflow.com/gone/, which is no page of the site")

    def test_a_missing_sitemap_fails(self):
        os.remove(os.path.join(self.root, "sitemap.xml"))
        self.assertFails("metadata: sitemap.xml is missing")

    def test_a_robots_txt_that_does_not_point_to_the_sitemap_fails(self):
        self.write("robots.txt", "User-agent: *\nAllow: /\n")
        self.assertFails("metadata: robots.txt has no line Sitemap: https://harmflow.com/sitemap.xml")

    # Landing page.

    def assertLandingFails(self, text, **parts):
        """The en-US index.html, built from PARTS, fails the landing check with one problem, which holds TEXT."""
        self.write("index.html", page("en-US", "index.html", **parts))
        lines = self.assertFails(text)
        self.assertEqual(len([line for line in lines if "landing:" in line]), 1, lines)

    def test_a_landing_page_with_no_community_edition_link_fails(self):
        self.assertLandingFails(
            "landing: index.html has no link to the community edition's build instructions, "
            "https://github.com/harmflow/harmflow-app#quick-start",
            landing="\n".join((BADGE, AUDIENCE, CTA)),
        )

    def test_a_community_edition_link_before_the_call_to_action_fails(self):
        self.assertLandingFails(
            "the community edition's link comes before the first primary call to action",
            landing="\n".join((BADGE, AUDIENCE, COMMUNITY, CTA)),
        )

    def test_a_community_edition_link_that_is_a_call_to_action_fails(self):
        community = COMMUNITY.replace("<a href", '<a class="cta" href')
        self.write("index.html", page("en-US", "index.html", landing="\n".join((BADGE, AUDIENCE, CTA, community))))
        self.assertFails("landing: index.html:", "the community edition's link is itself a primary call to action")

    # header-cta, the header's link, holds cta only as part of a token, so it is no primary call to action.
    def test_a_landing_page_with_no_call_to_action_fails(self):
        self.assertLandingFails(
            "landing: index.html has no primary call to action (an a.cta)",
            landing="\n".join((BADGE, AUDIENCE, CTA.replace('class="cta"', 'class="header-cta"'), COMMUNITY)),
        )

    def test_a_call_to_action_that_leads_elsewhere_fails(self):
        elsewhere = '<a class="hero cta" href="https://example.com/harmflow">Download</a>'
        self.assertLandingFails(
            "its primary call to action leads to https://example.com/harmflow, "
            "not https://github.com/harmflow/harmflow-app",
            landing="\n".join((BADGE, AUDIENCE, CTA, COMMUNITY, elsewhere)),
        )

    # The description and Open Graph tags say it, but the visitor reads only the body.
    def test_a_landing_page_that_does_not_say_it_is_coming_to_the_store_fails(self):
        text = page("en-US", "index.html", landing="\n".join((AUDIENCE, CTA, COMMUNITY)))
        self.write("index.html", text.replace("A page of the fixture.", "Coming to the Mac App Store."))
        lines = self.assertFails("landing: index.html does not say that HarmFlow is coming to the Mac App Store")
        self.assertEqual(len([line for line in lines if "landing:" in line]), 1, lines)

    def test_the_store_in_any_case_and_across_elements_passes(self):
        badge = '<p class="badge">COMING to the <em>Mac</em>\n  App Store</p>'
        self.write("index.html", page("en-US", "index.html", landing="\n".join((badge, AUDIENCE, CTA, COMMUNITY))))
        self.assertPasses()

    # The footer is read too, which also makes it differ from the other pages'.
    def test_a_link_to_the_mac_app_store_fails_wherever_it_is(self):
        link = '<a href="https://apps.apple.com/app/harmflow/id1">Get it</a>\n</footer>'
        self.write("index.html", page("en-US", "index.html", footer_html=footer("en-US").replace("</footer>", link)))
        lines = self.assertFails(
            "landing: index.html:", "https://apps.apple.com/app/harmflow/id1 leads to the Mac App Store"
        )
        self.assertEqual(len([line for line in lines if "landing:" in line]), 1, lines)

    # Whom the landing page is for: developers, on the Mac, who use Claude Code or Codex.

    def test_a_landing_page_that_does_not_say_it_is_for_developers_fails(self):
        lead = AUDIENCE.replace("For developers on the Mac", "On the Mac")
        self.assertLandingFails(
            "landing: index.html does not say that HarmFlow is for developers",
            landing="\n".join((BADGE, lead, CTA, COMMUNITY)),
        )

    # The badge still names the Mac App Store, which is not the visitor's computer.
    def test_a_landing_page_that_names_the_mac_only_in_the_store_fails(self):
        lead = AUDIENCE.replace("developers on the Mac", "developers")
        self.assertLandingFails(
            "landing: index.html does not name the Mac, other than in the Mac App Store's name",
            landing="\n".join((BADGE, lead, CTA, COMMUNITY)),
        )

    # macOS holds mac only as part of a word, so it does not name the Mac.
    def test_a_landing_page_that_names_macos_and_not_the_mac_fails(self):
        lead = AUDIENCE.replace("on the Mac", "on macOS")
        self.assertLandingFails(
            "landing: index.html does not name the Mac, other than in the Mac App Store's name",
            landing="\n".join((BADGE, lead, CTA, COMMUNITY)),
        )

    def test_a_landing_page_that_does_not_name_the_mac_at_all_fails(self):
        lead = AUDIENCE.replace("developers on the Mac", "developers")
        self.write("index.html", page("en-US", "index.html", landing="\n".join((lead, CTA, COMMUNITY))))
        lines = self.assertFails(
            "landing: index.html does not name the Mac, other than in the Mac App Store's name",
            "landing: index.html does not say that HarmFlow is coming to the Mac App Store",
        )
        self.assertEqual(len([line for line in lines if "landing:" in line]), 2, lines)

    def test_a_landing_page_that_does_not_name_a_harness_fails_naming_it(self):
        for name, lead in (
            ("Claude Code", AUDIENCE.replace("Claude Code and Codex", "Codex")),
            ("Codex", AUDIENCE.replace("Claude Code and Codex", "Claude Code")),
        ):
            with self.subTest(name=name):
                self.assertLandingFails(
                    "landing: index.html does not name %s" % name,
                    landing="\n".join((BADGE, lead, CTA, COMMUNITY)),
                )

    def test_a_landing_page_that_names_its_audience_in_any_case_and_across_elements_passes(self):
        lead = '<p>FOR <strong>Developers</strong> on the <em>mac</em>: <code>claude</code>\n  CODE and CODEX.</p>'
        self.write("index.html", page("en-US", "index.html", landing="\n".join((BADGE, lead, CTA, COMMUNITY))))
        self.assertPasses()

    # The footer every page shares names Claude Code, Codex, and the Mac, in its sentence and its trademark notes, but
    # it is not the landing page's own text.
    def test_a_landing_page_whose_main_drops_them_while_its_footer_names_them_fails(self):
        shared = footer("en-US").replace(
            "</footer>",
            "  <p>Schedules, runs, and monitors automations through Claude Code and Codex, on your Mac.</p>\n"
            "  <p>Claude Code is a trademark of Anthropic, PBC. Codex is a trademark of OpenAI. Mac and Mac App Store "
            "are trademarks of Apple Inc.</p>\n</footer>",
        )
        lead = '<p class="lead">For developers: HarmFlow runs your automations on a schedule.</p>'
        for slug in SLUGS:
            landing = "\n".join((BADGE, lead, CTA, COMMUNITY)) if slug == "index.html" else None
            self.write(slug, page("en-US", slug, footer_html=shared, landing=landing))
        lines = self.assertFails(
            "landing: index.html does not name the Mac, other than in the Mac App Store's name",
            "landing: index.html does not name Claude Code",
            "landing: index.html does not name Codex",
        )
        self.assertEqual(len([line for line in lines if "landing:" in line]), 3, lines)

    # The title, the description, the Open Graph tags, an alt text, and an aria-label name them, but no visitor reads
    # them on the page.
    def test_a_landing_page_that_names_them_only_in_its_head_and_attributes_fails(self):
        names = "For developers on the Mac who use Claude Code or Codex"
        lead = '<div class="feature-art" role="img" aria-label="%s"></div>' % names
        text = page("en-US", "index.html", landing="\n".join((BADGE, lead, CTA, COMMUNITY)))
        text = text.replace("A page of the fixture.", names + ".").replace("<title>A page", "<title>" + names)
        self.write("index.html", text.replace('alt=""', 'alt="%s"' % names))
        lines = self.assertFails(
            "landing: index.html does not say that HarmFlow is for developers",
            "landing: index.html does not name the Mac, other than in the Mac App Store's name",
            "landing: index.html does not name Claude Code",
            "landing: index.html does not name Codex",
        )
        self.assertEqual(len([line for line in lines if "landing:" in line]), 4, lines)

    # The privacy policy.

    def test_a_privacy_policy_with_no_heading_for_a_part_fails_naming_it(self):
        for part_id, part in PRIVACY_PARTS:
            with self.subTest(part=part_id):
                text = page("en-US", "privacy/index.html").replace(' id="%s"' % part_id, "")
                self.write("privacy/index.html", text)
                lines = self.assertFails(
                    "privacy: privacy/index.html has no heading with the id %s, for its part on %s" % (part_id, part)
                )
                self.assertEqual(len([line for line in lines if "privacy:" in line]), 1, lines)
        self.write("privacy/index.html", page("en-US", "privacy/index.html"))
        self.assertPasses()

    # A part ends at the next heading of any level, or where the element that holds it ends: an h3's text is not the h2
    # part's above it, and the footer's text after the last part is not that part's.
    def test_a_privacy_policy_part_with_no_text_fails_naming_it(self):
        analytics = "  <p>It measures its visits with Google Analytics, once you accept.</p>\n"
        cases = (
            ("app", "the HarmFlow app", ((APP_PART, ""),)),
            # The page still names Google Analytics, in the google part, so only the empty part fails.
            (
                "analytics",
                "analytics",
                ((analytics, ""), ("Google receives each", "Google Analytics sends Google each")),
            ),
            ("retention", "how long the data is kept", ((RETENTION_PART, ""),)),
            ("withdraw", "withdrawing consent", ((WITHDRAW_PART, ""),)),
        )
        for part_id, part, edits in cases:
            with self.subTest(part=part_id):
                text = page("pt-BR", "privacy/index.html")
                for old, new in edits:
                    self.assertIn(old, text)
                    text = text.replace(old, new)
                self.write("pt-br/privacy/index.html", text)
                lines = self.assertFails(
                    "privacy: pt-br/privacy/index.html: its part on %s (#%s) has no text after its heading"
                    % (part, part_id)
                )
                self.assertEqual(len([line for line in lines if "privacy:" in line]), 1, lines)

    def test_a_privacy_policy_that_does_not_name_google_analytics_fails(self):
        text = page("es-ES", "privacy/index.html").replace("Google Analytics", "a measurement service")
        self.write("es-es/privacy/index.html", text)
        self.assertFails("privacy: es-es/privacy/index.html does not name Google Analytics")

    # What the policy's parts say.

    def assertSaysFails(self, rel, text, problem):
        """The page REL, written as TEXT, fails with PROBLEM, the one problem of its kind (privacy: or support:)."""
        self.write(rel, text)
        kind = problem.split(":")[0] + ":"
        lines = self.assertFails(problem)
        self.assertEqual([line for line in lines if kind in line], ["check-site: " + problem], lines)

    def edited(self, language, slug, *edits):
        """The fixture's page with each (OLD, NEW) of EDITS made; OLD must be in it, so a case cannot pass unbroken."""
        text = page(language, slug)
        for old, new in edits:
            self.assertIn(old, text)
            text = text.replace(old, new)
        return text

    def test_a_privacy_policy_whose_app_part_does_not_say_it_sends_nothing_fails(self):
        self.assertSaysFails(
            "privacy/index.html",
            self.edited("en-US", "privacy/index.html", ("sends nothing to HarmFlow", "sends little to HarmFlow")),
            "privacy: privacy/index.html: its part on the HarmFlow app (#app) does not say that the app sends nothing "
            "to HarmFlow",
        )

    # Another part's text is not the app's.
    def test_a_privacy_policy_that_says_the_app_sends_nothing_only_in_another_part_fails(self):
        self.assertSaysFails(
            "pt-br/privacy/index.html",
            self.edited(
                "pt-BR",
                "privacy/index.html",
                (APP_PART, "  <p>What it keeps stays on your Mac.</p>\n"),
                ("no cookie of its own.", "no cookie of its own, and the app sends nothing to HarmFlow."),
            ),
            "privacy: pt-br/privacy/index.html: its part on the HarmFlow app (#app) does not say that the app sends "
            "nothing to HarmFlow",
        )

    def test_a_privacy_policy_whose_app_part_does_not_say_what_it_keeps_stays_on_the_mac_fails(self):
        self.assertSaysFails(
            "privacy/index.html",
            self.edited("en-US", "privacy/index.html", ("what it keeps stays on your Mac", "what it keeps is yours")),
            "privacy: privacy/index.html: its part on the HarmFlow app (#app) does not say that what the app keeps "
            "stays on the Mac",
        )

    def test_a_privacy_policy_that_does_not_give_the_retention_period_fails(self):
        self.assertSaysFails(
            "privacy/index.html",
            self.edited("en-US", "privacy/index.html", ("for two months", "for a while")),
            "privacy: privacy/index.html: its part on how long the data is kept (#retention) does not give the period "
            "Google Analytics keeps the detailed data, two months",
        )

    def test_a_privacy_policy_that_does_not_say_a_return_visit_keeps_the_period_fails(self):
        self.assertSaysFails(
            "es-es/privacy/index.html",
            self.edited(
                "es-ES",
                "privacy/index.html",
                ("does not extend that period when you come back", "starts it again when you come back"),
            ),
            "privacy: es-es/privacy/index.html: its part on how long the data is kept (#retention) does not say that "
            "a return visit does not extend that period",
        )

    def test_a_withdrawal_part_that_does_not_say_the_link_is_in_the_footer_fails(self):
        self.assertSaysFails(
            "privacy/index.html",
            self.edited("en-US", "privacy/index.html", ("in the footer of every page", "on every page")),
            "privacy: privacy/index.html: its part on withdrawing consent (#withdraw) does not say that the link that "
            "reopens the choice is in the footer",
        )

    # The footer holds the label, but only the part's own text is read.
    def test_a_withdrawal_part_that_does_not_name_the_footer_link_fails_naming_its_label(self):
        self.assertSaysFails(
            "privacy/index.html",
            self.edited("en-US", "privacy/index.html", ("Use the Analytics choice link", "Use the link")),
            "privacy: privacy/index.html: its part on withdrawing consent (#withdraw) does not name \"Analytics "
            "choice\", the label of the footer's link that reopens the choice",
        )

    # The footer every page shares renames its link, and the policy still names the old label: each published
    # language's policy fails, naming the label it no longer finds, and nothing else does.
    def test_a_footer_link_renamed_under_the_policy_fails_naming_the_new_label(self):
        for language, prefix in PREFIXES:
            renamed = footer(language).replace(">Analytics choice<", ">Cookie settings<")
            for slug in SLUGS:
                self.write(prefix + slug, page(language, slug, footer_html=renamed))
        problem = (
            "privacy: %sprivacy/index.html: its part on withdrawing consent (#withdraw) does not name \"Cookie "
            "settings\", the label of the footer's link that reopens the choice"
        )
        lines = self.assertFails(problem % "")
        self.assertEqual(sorted(lines), sorted("check-site: " + problem % prefix for _, prefix in PREFIXES), lines)

    def test_a_footer_with_no_link_that_reopens_the_choice_fails_naming_the_page(self):
        for language, prefix in PREFIXES:
            plain = footer(language).replace(" data-consent-choice", "")
            for slug in SLUGS:
                self.write(prefix + slug, page(language, slug, footer_html=plain))
        problem = (
            "privacy: %sprivacy/index.html: its footer has no labeled link with data-consent-choice that reopens the "
            "choice, so its part on withdrawing consent (#withdraw) names no control the visitor can find"
        )
        lines = self.assertFails(problem % "")
        self.assertEqual(sorted(lines), sorted("check-site: " + problem % prefix for _, prefix in PREFIXES), lines)

    # A part runs to the next heading of its own level or a higher one, so a subheading's text is its part's.
    def test_a_part_whose_words_are_under_its_subheading_passes(self):
        subheading = (
            "  <p>It runs on your Mac.</p>\n  <h3 id=\"keeps\">What it keeps</h3>\n%s  <h4>Its data</h4>\n"
            "  <p>Your tasks are files.</p>\n" % APP_PART
        )
        self.write("privacy/index.html", self.edited("en-US", "privacy/index.html", (APP_PART, subheading)))
        self.assertPasses()

    def test_what_the_pages_say_in_any_case_and_across_elements_passes(self):
        self.write(
            "privacy/index.html",
            self.edited(
                "en-US",
                "privacy/index.html",
                ("It sends nothing to HarmFlow", "It <em>SENDS nothing</em>\n  to HarmFlow"),
                ("what it keeps stays on your Mac", "What it keeps <strong>stays on your MAC</strong>"),
                ("for two months", "for Two <b>Months</b>"),
                ("does not extend that period when", "Does Not extend that period <em>when</em>\n "),
                ("Use the Analytics choice link in the footer", "Use the analytics CHOICE link <em>in the</em> Footer"),
            ),
        )
        self.write(
            "support/index.html",
            self.edited(
                "en-US",
                "support/index.html",
                ("The issues are not a support channel.", "<strong>THE issues</strong> are not a\n  support channel."),
            ),
        )
        self.assertPasses()

    # The support page.

    def test_a_support_page_with_no_link_to_the_issues_fails(self):
        text = page("en-US", "support/index.html").replace(
            "https://github.com/harmflow/harmflow-app/issues/new/choose", "https://github.com/harmflow/harmflow-app"
        )
        self.write("support/index.html", text)
        self.assertFails(
            "support: support/index.html has no link to https://github.com/harmflow/harmflow-app/issues"
        )

    def test_a_link_to_the_issues_themselves_passes_and_a_lookalike_fails(self):
        issues = "https://github.com/harmflow/harmflow-app/issues"
        text = page("en-US", "support/index.html").replace(issues + "/new/choose", issues)
        self.write("support/index.html", text)
        self.assertPasses()
        self.write("support/index.html", text.replace(issues, issues + "-archive"))
        self.assertFails("support: support/index.html has no link to " + issues)

    def test_a_support_page_with_a_mailto_link_fails_naming_the_address(self):
        body = '<p><a href="mailto:help@example.com?subject=HarmFlow">Write to us</a></p>'
        self.write("support/index.html", page("en-US", "support/index.html", body=body))
        self.assertFails(
            "support: support/index.html gives the e-mail address help@example.com; the support page gives none"
        )

    def test_a_support_page_with_an_e_mail_address_in_its_text_fails_naming_it(self):
        body = "<p>Or write to help@example.com.</p>"
        self.write("pt-br/support/index.html", page("pt-BR", "support/index.html", body=body))
        self.assertFails("support: pt-br/support/index.html gives the e-mail address help@example.com")

    def test_an_e_mail_address_on_another_page_passes(self):
        body = "<p>Or write to help@example.com.</p>"
        self.write("privacy/index.html", page("en-US", "privacy/index.html", body=body))
        self.write("index.html", page("en-US", "index.html", body=body))
        self.assertPasses()

    def test_a_support_page_that_does_not_say_the_issues_are_not_support_fails(self):
        self.assertSaysFails(
            "support/index.html",
            self.edited("en-US", "support/index.html", (NOT_SUPPORT, "<p>The issues are read every day.</p>")),
            "support: support/index.html does not say that the issues are not support",
        )

    # The page's own text is its main's, or its part's: the shared header and footer, the title, the description, the
    # Open Graph tags, alt text, and aria-label attributes say it to no visitor reading the page.
    def test_what_the_pages_say_only_outside_their_text_fails(self):
        cases = (
            (
                "support/index.html",
                "The issues are not a support channel",
                (NOT_SUPPORT, ""),
                "support: support/index.html does not say that the issues are not support",
            ),
            (
                "privacy/index.html",
                "The app sends nothing to HarmFlow",
                ("It sends nothing to HarmFlow", "It sends little to HarmFlow"),
                "privacy: privacy/index.html: its part on the HarmFlow app (#app) does not say that the app sends "
                "nothing to HarmFlow",
            ),
        )
        for slug, words, edit, problem in cases:
            with self.subTest(page=slug):
                self.setUp()
                blocks = (
                    ("</header>", "  <p>%s.</p>\n</header>" % words),
                    ("</footer>", "  <p>%s.</p>\n</footer>" % words),
                )
                head_and_attributes = (
                    ("<title>A page</title>", "<title>%s</title>" % words),
                    ('content="A page of the fixture."', 'content="%s."' % words),
                    ('alt=""', 'alt="%s"' % words),
                    ('<a href="#top">Top</a>', '<a href="#top" aria-label="%s">Top</a>' % words),
                )
                # Every en-US page shares the header and footer, so only the rule this case breaks fails.
                for other in SLUGS:
                    if other != slug:
                        self.write(other, self.edited("en-US", other, *blocks))
                self.assertSaysFails(slug, self.edited("en-US", slug, *(blocks + head_and_attributes + (edit,))), problem)

    # With no privacy policy or support page, the footer's links to them fail, and so do their two required paths;
    # nothing else does.
    def test_a_tree_with_no_privacy_or_support_page_fails_only_its_links_and_paths(self):
        for _, prefix in PREFIXES:
            shutil.rmtree(os.path.join(self.root, prefix + "privacy"))
            shutil.rmtree(os.path.join(self.root, prefix + "support"))
        kept = [slug for slug in SLUGS if slug not in ("privacy/index.html", "support/index.html")]
        self.write("sitemap.xml", sitemap(prefix + slug for _, prefix in PREFIXES for slug in kept))
        lines = self.assertFails(
            "links: index.html:", "/privacy/ leads to no file", "/support/#contact leads to no file"
        )
        self.assertEqual(
            [line for line in lines if not line.startswith("check-site: links: ")],
            [
                "check-site: paths: /privacy/ has no page: privacy/index.html is missing",
                "check-site: paths: /support/ has no page: support/index.html is missing",
            ],
            lines,
        )

    # The user guide.

    def assertGuideFails(self, text):
        """The check fails with one guide problem, TEXT."""
        lines = self.assertFails(text)
        self.assertEqual([line for line in lines if "guide:" in line], ["check-site: " + text], lines)

    def test_a_guide_index_missing_a_parts_link_fails_naming_it(self):
        text = page("en-US", "docs/guide/index.html")
        self.assertIn(GUIDE_LINKS[1], text)
        self.write("docs/guide/index.html", text.replace(GUIDE_LINKS[1], ""))
        self.assertGuideFails(
            "guide: docs/guide/index.html: its main does not link to /docs/guide/repository-access/ "
            "(Granting access to repositories)"
        )

    def test_a_guide_index_listing_the_parts_out_of_order_fails_naming_the_part(self):
        text = page("en-US", "docs/guide/index.html")
        swapped = text.replace(GUIDE_LINKS[1], "(moved)").replace(GUIDE_LINKS[2], GUIDE_LINKS[1])
        self.write("docs/guide/index.html", swapped.replace("(moved)", GUIDE_LINKS[2]))
        self.assertGuideFails(
            "guide: docs/guide/index.html: its main links to /docs/guide/tasks/ (Creating tasks) before "
            "/docs/guide/repository-access/ (Granting access to repositories), out of the parts' order"
        )

    # The links lead to the parts whatever form they take: relative, to the index.html, or at harmflow.com.
    def test_links_to_the_parts_in_another_form_pass(self):
        text = page("en-US", "docs/guide/index.html")
        text = text.replace('href="/docs/guide/install/"', 'href="install/index.html"')
        text = text.replace('href="/docs/guide/tasks/"', 'href="https://harmflow.com/docs/guide/tasks/"')
        self.write("docs/guide/index.html", text.replace('href="/docs/guide/executions/"', 'href="executions"'))
        self.assertPasses()

    # Removed with its sitemap entry, in the site as it is published: the index's link to it fails too.
    def test_a_guide_part_removed_fails_naming_its_path(self):
        self.en_us_only()
        os.remove(os.path.join(self.root, "docs/guide/tasks/index.html"))
        self.write("sitemap.xml", sitemap(slug for slug in SLUGS if slug != "docs/guide/tasks/index.html"))
        lines = self.assertFails(
            "guide: /docs/guide/tasks/ (Creating tasks) has no page: docs/guide/tasks/index.html is missing",
            languages=[],
        )
        self.assertEqual(len([line for line in lines if "guide:" in line]), 1, lines)

    def test_a_guide_part_whose_heading_names_another_subject_fails_naming_it(self):
        text = page("en-US", "docs/guide/tasks/index.html")
        self.assertIn(">Creating tasks</h1>", text)
        self.write("docs/guide/tasks/index.html", text.replace(">Creating tasks</h1>", ">Reading executions</h1>"))
        self.assertGuideFails(
            'guide: docs/guide/tasks/index.html: its h1 is "Reading executions", not "Creating tasks"'
        )

    def test_a_guide_part_that_is_still_a_stub_fails_naming_it(self):
        text = page("en-US", "docs/guide/executions/index.html")
        self.assertIn(INTRODUCTION, text)
        stub = text.replace(INTRODUCTION, "<p>This page is being written.</p>")
        self.write("docs/guide/executions/index.html", stub)
        self.assertGuideFails('guide: docs/guide/executions/index.html still reads "This page is being written."')

    def test_a_guide_part_with_no_paragraph_fails_naming_it(self):
        text = re.sub(r"<p>.*?</p>", "", page("en-US", "docs/guide/install/index.html"))
        self.assertNotIn("<p>", text)
        self.write("docs/guide/install/index.html", text)
        self.assertGuideFails(
            "guide: docs/guide/install/index.html: its main has no paragraph of text beyond its heading"
        )

    def add_guide_section(self, section=None, part_link=GUIDE_SECTION_LINK):
        """The site as it is published, in en-US only, with one section under the tasks part: SECTION as its page, a
        well-formed one by default, listed in the sitemap, and the part's page holding PART_LINK in its main. The other
        three parts have no section."""
        self.en_us_only()
        if section is None:
            section = page("en-US", GUIDE_SECTION, header_html=EN_US_HEADER, body=GUIDE_SECTION_TEXT)
        self.write(GUIDE_SECTION, section)
        part = page("en-US", "docs/guide/tasks/index.html", header_html=EN_US_HEADER, body=part_link)
        self.write("docs/guide/tasks/index.html", part)
        self.write("sitemap.xml", sitemap(SLUGS + (GUIDE_SECTION,)))

    def assertGuideSectionFails(self, text):
        """The site as it is published fails with one guide problem, TEXT."""
        lines = self.assertFails(text, languages=[])
        self.assertEqual([line for line in lines if "guide:" in line], ["check-site: " + text], lines)

    # A section listed by its part passes, while the other parts, as repository-access/ is today, have none.
    def test_a_guide_section_linked_from_its_part_passes(self):
        self.add_guide_section()
        self.assertPasses(languages=[])

    # The part's link leads to its section whatever form it takes: relative, to the index.html, or at harmflow.com.
    def test_links_to_a_guide_section_in_another_form_pass(self):
        self.add_guide_section()
        for href in ("yaml-tab", "yaml-tab/index.html", "https://harmflow.com/docs/guide/tasks/yaml-tab/"):
            with self.subTest(href=href):
                link = '<p><a href="%s">Editing a task as YAML</a></p>' % href
                part = page("en-US", "docs/guide/tasks/index.html", header_html=EN_US_HEADER, body=link)
                self.write("docs/guide/tasks/index.html", part)
                self.assertPasses(languages=[])

    def test_a_guide_section_its_part_does_not_link_to_fails_naming_it(self):
        self.add_guide_section(part_link="")
        self.assertGuideSectionFails(
            "guide: docs/guide/tasks/yaml-tab/index.html: its part's page docs/guide/tasks/index.html "
            "does not link to it"
        )

    def test_a_guide_section_with_no_h1_fails_naming_it(self):
        text = page("en-US", GUIDE_SECTION, header_html=EN_US_HEADER, body=GUIDE_SECTION_TEXT)
        self.assertIn('<h1 id="title">A page</h1>', text)
        self.add_guide_section(section=text.replace('<h1 id="title">A page</h1>', '<h2 id="title">A page</h2>'))
        self.assertGuideSectionFails("guide: docs/guide/tasks/yaml-tab/index.html: its main has no h1")

    def test_a_guide_section_that_is_still_a_stub_fails_naming_it(self):
        stub = page("en-US", GUIDE_SECTION, header_html=EN_US_HEADER, body="<p>This page is being written.</p>")
        self.add_guide_section(section=stub)
        self.assertGuideSectionFails(
            'guide: docs/guide/tasks/yaml-tab/index.html still reads "This page is being written."'
        )

    def test_a_guide_section_with_no_paragraph_fails_naming_it(self):
        text = re.sub(r"<p>.*?</p>", "", page("en-US", GUIDE_SECTION, header_html=EN_US_HEADER))
        self.assertNotIn("<p>", text)
        self.add_guide_section(section=text)
        self.assertGuideSectionFails(
            "guide: docs/guide/tasks/yaml-tab/index.html: its main has no paragraph of text beyond its heading"
        )

    # The root 404 page.

    def test_a_tree_with_pages_and_no_root_404_page_fails(self):
        os.remove(os.path.join(self.root, "404.html"))
        lines = self.assertFails("not found: 404.html is missing")
        self.assertEqual(len([line for line in lines if "not found:" in line]), 1, lines)

    def test_a_404_page_with_no_heading_that_says_not_found_fails(self):
        self.write("404.html", NOT_FOUND.replace("<h1>Page not found</h1>", "<h1>Oops</h1>"))
        self.assertFails("not found: 404.html: its main has no heading that says the page was not found")

    def test_a_not_found_heading_outside_main_fails(self):
        moved = NOT_FOUND.replace("  <h1>Page not found</h1>\n", "").replace(
            "</a></header>", "</a><h1>Page not found</h1></header>"
        )
        self.write("404.html", moved)
        self.assertFails("not found: 404.html: its main has no heading that says the page was not found")

    def test_a_not_found_heading_in_any_case_passes(self):
        self.write("404.html", NOT_FOUND.replace("<h1>Page not found</h1>", "<h2>404 · <em>Not  Found</em></h2>"))
        self.assertPasses()

    # The header's link home is outside main, so it does not count.
    def test_a_404_page_with_no_link_to_the_landing_page_fails(self):
        self.write("404.html", NOT_FOUND.replace('<p><a href="/">Home</a></p>', '<p><a href="/support/">Help</a></p>'))
        self.assertFails("not found: 404.html: its main has no link to the landing page (/ or https://harmflow.com/)")

    def test_a_link_to_the_landing_page_at_harmflow_com_passes(self):
        self.write("404.html", NOT_FOUND.replace('<a href="/">Home</a>', '<a href="https://harmflow.com/">Home</a>'))
        self.assertPasses()

    # Each of these resolves from the root, where the file sits, so only the 404 page's own rule sees it break.
    def test_a_relative_link_in_the_404_page_fails_naming_the_attribute_and_value(self):
        self.write("404.html", NOT_FOUND.replace('<a href="/">Home</a>', '<a href="/">Home</a> <a href="privacy/">x</a>'))
        lines = self.assertFails("not found: 404.html:", 'href="privacy/" is a relative path')
        self.assertEqual([line for line in lines if "links:" in line], [], lines)

    def test_a_relative_asset_in_the_404_page_fails_naming_the_attribute_and_value(self):
        styled = NOT_FOUND.replace("<head>", '<head><link rel="stylesheet" href="styles/site.css">')
        self.write("404.html", styled.replace("<h1>", '<img src="showroom/poster.png" alt=""><h1>'))
        self.assertFails('href="styles/site.css" is a relative path', 'src="showroom/poster.png" is a relative path')

    def test_a_relative_srcset_candidate_in_the_404_page_fails(self):
        image = '<img src="/showroom/poster.png" srcset="/showroom/poster.png 1x, ./showroom/poster.png 2x" alt="">'
        self.write("404.html", NOT_FOUND.replace("<h1>", image + "<h1>"))
        lines = self.assertFails('srcset="./showroom/poster.png" is a relative path')
        self.assertEqual(len([line for line in lines if "not found:" in line]), 1, lines)

    def test_root_paths_absolute_urls_and_anchors_in_the_404_page_pass(self):
        links = (
            '<p><a href="#top">Top</a> <a href="https://github.com/harmflow/harmflow-app">The app</a> '
            '<a href="mailto:support@example.com">Mail</a> <a href="/privacy/">Privacy</a></p>'
        )
        self.write("404.html", NOT_FOUND.replace("</main>", links + "\n</main>"))
        self.assertPasses()

    # Colors.

    def assertColorFails(self, *texts):
        """The check fails with one colors problem, and its output holds each of TEXTS."""
        lines = self.assertFails(*texts)
        self.assertEqual(len([line for line in lines if "colors:" in line]), 1, lines)

    def test_a_hex_color_that_is_neither_fails_naming_it(self):
        self.write("styles/landing.css", ".tag {\n  color: #c4b5fd;\n}\n")
        self.assertColorFails(
            "colors: styles/landing.css:2: #c4b5fd is neither one of the logo's colors nor a placeholder"
        )

    def test_an_rgb_color_that_is_neither_fails_naming_it(self):
        self.write("styles/landing.css", ".window { box-shadow: 0 40px 120px rgb(0 0 0 / 0.6); }\n")
        self.assertColorFails("colors: styles/landing.css:1: rgb(0 0 0 / 0.6) is neither")

    def test_an_hsl_color_that_is_neither_fails_naming_it(self):
        self.write("styles/landing.css", ".badge {\n  margin: 0;\n  border-color: hsla(200, 50%, 40%, 0.5);\n}\n")
        self.assertColorFails("colors: styles/landing.css:3: hsla(200, 50%, 40%, 0.5) is neither")

    def test_a_named_color_that_is_neither_fails_naming_it(self):
        self.write("styles/landing.css", ".cta { color: White; background: transparent; border-color: currentColor; }\n")
        self.assertColorFails("colors: styles/landing.css:1: White is neither")

    def test_a_page_style_attribute_with_a_color_that_is_neither_fails_naming_it(self):
        body = '<p style="margin: 0;\n  color: #123456">A note</p>'
        self.write("privacy/index.html", page("en-US", "privacy/index.html", body=body))
        self.assertColorFails("colors: privacy/index.html:", "#123456 is neither")

    def test_a_page_style_element_with_a_color_that_is_neither_fails_naming_its_line(self):
        style = "<style>\n  .note { margin: 0; }\n  .note { color: rgb(18, 52, 86); }\n</style>"
        text = page("en-US", "support/index.html").replace("</head>", style + "\n</head>")
        self.write("support/index.html", text)
        line = text.split("\n").index("  .note { color: rgb(18, 52, 86); }") + 1
        self.assertColorFails("colors: support/index.html:%d: rgb(18, 52, 86) is neither" % line)

    # A custom property declares no placeholder outside site.css's :root block.
    def test_a_custom_property_outside_the_placeholder_block_fails(self):
        self.write("styles/landing.css", ".landing { --raised: #121829; }\n.window { background: var(--raised); }\n")
        self.assertColorFails("colors: styles/landing.css:1: #121829 is neither")

    def test_a_logo_color_at_an_opacity_passes(self):
        css = (
            ".landing { --logo-violet: #8b5cf6; --logo-cyan: #22D3EE; }\n"
            ".tag { background: rgb(139 92 246 / 0.15); border-color: #e040fb80; }\n"
            ".tag.running { background: rgba(34, 211, 238, 0.12); color: var(--logo-cyan); }\n"
        )
        self.write("styles/landing.css", css)
        self.assertPasses()

    def test_a_placeholder_through_its_custom_property_or_its_value_at_an_opacity_passes(self):
        css = ".site-header { background: rgb(11 15 26 / 0.72); color: var(--text); border-color: #0b0f1a; }\n"
        self.write("styles/landing.css", css)
        self.write("index.html", page("en-US", "index.html", body='<p style="color: var(--text)">A note</p>'))
        self.assertPasses()

    # What a value does not say is no color: a comment, a string, a url(), an at-rule's condition, or a word that only
    # holds a color's name, as --logo-cyan and white-space do.
    def test_a_color_outside_a_value_passes(self):
        css = (
            "/* Not #c4b5fd, nor red. */\n"
            '@font-face { font-family: "Red Hat"; src: url("/fonts/inter/inter.woff2#fff") format("woff2"); }\n'
            "@media (max-width: 52rem) { .cta { white-space: nowrap; color: var(--logo-cyan); } }\n"
            "#fff, .red { margin: 0; }\n"
        )
        self.write("styles/landing.css", css)
        self.assertPasses()

    # Media budget.

    def test_a_media_file_over_10_mb_fails_naming_it_and_the_limit(self):
        self.sparse("showroom/demo.mp4", 12 * MB)
        self.assertFails("media: showroom/demo.mp4 is 12,000,000 bytes, over the 10 MB limit")

    def test_a_media_file_of_10_mb_passes(self):
        self.sparse("showroom/demo.mp4", 10 * MB)
        self.assertPasses()

    def test_media_over_300_mb_together_fail_naming_the_limit(self):
        for i in range(31):
            self.sparse("showroom/clip-%02d.webm" % i, 9900 * 1000)
        lines = self.assertFails("over the 300 MB limit for all media together")
        self.assertEqual(len([line for line in lines if "media:" in line]), 1, lines)

    # Typefaces.

    def test_a_font_from_another_host_fails_naming_the_stylesheet_and_the_family(self):
        self.restyle('url("/fonts/inter/inter.woff2")', 'url("https://fonts.example.com/inter.woff2")')
        self.assertFails(
            "fonts: styles/site.css: the Inter rule takes https://fonts.example.com/inter.woff2 from another host"
        )

    def test_a_font_in_another_format_fails(self):
        self.restyle('"/fonts/inter/inter.woff2") format("woff2")', '"/fonts/inter/inter.ttf") format("truetype")')
        self.write("fonts/inter/inter.ttf", "not really a font\n")
        self.assertFails(
            "fonts: styles/site.css: the Inter rule takes /fonts/inter/inter.ttf, which is not a .woff2 file under "
            "/fonts/",
            'fonts: styles/site.css: the Inter rule takes /fonts/inter/inter.ttf without format("woff2")',
        )

    def test_a_woff2_file_with_another_format_hint_fails(self):
        self.restyle("format('woff2')", "format('woff')")
        self.assertFails(
            "fonts: styles/site.css: the JetBrains Mono rule takes ../fonts/jetbrains-mono/jetbrains-mono.woff2 "
            'without format("woff2")'
        )

    def test_a_woff2_file_that_is_not_woff2_inside_fails(self):
        self.write("fonts/inter/inter.woff2", "wOFF a WOFF 1.0 font\n")
        self.assertFails(
            "fonts: styles/site.css: the Inter rule takes /fonts/inter/inter.woff2, which is not a WOFF2 file: "
            "it does not start with wOF2"
        )

    def test_a_font_rule_naming_a_missing_file_fails(self):
        os.remove(os.path.join(self.root, "fonts/jetbrains-mono/jetbrains-mono.woff2"))
        self.assertFails(
            "fonts: styles/site.css: the JetBrains Mono rule takes ../fonts/jetbrains-mono/jetbrains-mono.woff2, "
            "which is no file of the site"
        )

    def test_a_font_outside_the_fonts_folder_fails(self):
        self.restyle('"/fonts/inter/inter.woff2"', '"/styles/inter.woff2"')
        self.write("styles/inter.woff2", WOFF2)
        self.assertFails("the Inter rule takes /styles/inter.woff2, which is not a .woff2 file under /fonts/")

    def test_a_family_folder_with_no_license_fails_naming_it(self):
        os.remove(os.path.join(self.root, "fonts/inter/LICENSE"))
        self.assertFails("fonts: fonts/inter has no LICENSE beside its fonts")

    def test_a_family_folder_with_another_license_fails_naming_it(self):
        self.write("fonts/jetbrains-mono/LICENSE", "Apache License\nVersion 2.0, January 2004\n")
        self.assertFails("fonts: fonts/jetbrains-mono/LICENSE is not the SIL Open Font License 1.1")

    def test_a_stack_with_no_fallback_fails_naming_it(self):
        self.restyle('--font-text: "Inter", system-ui, sans-serif;', '--font-text: "Inter";')
        self.assertFails("fonts: styles/site.css: --font-text (Inter) does not end in sans-serif")

    def test_a_stack_with_no_system_font_fails_naming_it(self):
        self.restyle("ui-monospace, Menlo, monospace", "monospace")
        self.assertFails(
            "fonts: styles/site.css: --font-mono (JetBrains Mono, monospace) names no system font between "
            "JetBrains Mono and monospace"
        )

    def test_a_site_with_no_stack_fails(self):
        self.restyle('  --font-mono: "JetBrains Mono", ui-monospace, Menlo, monospace;\n', "")
        self.assertFails("fonts: no stylesheet declares --font-mono, the stack of JetBrains Mono")

    # Posters. Every case writes the recording and the poster its <video> names, so only the poster rule can fail.

    def with_video(self, video):
        self.write("showroom/demo.mp4", "not really an mp4\n")
        self.write("showroom/demo.webm", "not really a webm\n")
        self.write("index.html", page("en-US", "index.html", body=video))

    def assertOnePosterProblem(self, *texts):
        lines = self.assertFails(*texts)
        self.assertEqual([line for line in lines if "posters:" in line], lines, lines)
        self.assertEqual(len(lines), 1, lines)

    def test_a_video_with_no_poster_fails_naming_the_page(self):
        self.with_video('<video src="/showroom/demo.mp4" controls></video>')
        self.assertOnePosterProblem("posters: index.html:", "the video /showroom/demo.mp4 has no poster")

    def test_a_video_with_an_empty_poster_fails_naming_the_page(self):
        self.with_video('<video src="/showroom/demo.mp4" poster="" controls></video>')
        self.assertOnePosterProblem("posters: index.html:", "the video /showroom/demo.mp4 has an empty poster")

    def test_a_video_with_a_bare_poster_attribute_fails_as_empty(self):
        self.with_video("<video poster controls>\n  <source src=\"/showroom/demo.mp4\" type=\"video/mp4\">\n</video>")
        self.assertOnePosterProblem("posters: index.html:", "the video /showroom/demo.mp4 has an empty poster")

    def test_a_video_whose_poster_is_a_recording_fails_naming_the_poster(self):
        self.with_video('<video src="/showroom/demo.mp4" poster="/showroom/demo.webm" controls></video>')
        self.assertOnePosterProblem(
            "posters: index.html:",
            "the video /showroom/demo.mp4 has the poster /showroom/demo.webm, which is not an image file",
        )

    def test_a_video_with_an_image_poster_passes(self):
        self.with_video('<video src="/showroom/demo.mp4" poster="/showroom/poster.png" controls></video>')
        self.assertPasses()

    def test_a_video_whose_source_is_a_child_with_an_image_poster_passes(self):
        video = """<video poster="../showroom/poster.png" controls>
    <source src="/showroom/demo.webm" type="video/webm">
    <source src="/showroom/demo.mp4" type="video/mp4">
  </video>"""
        self.with_video(video)
        self.assertPasses()

    def test_a_video_whose_source_is_a_child_with_no_poster_fails_naming_that_source(self):
        self.with_video('<video controls>\n  <source src="/showroom/demo.webm" type="video/webm">\n</video>')
        self.assertOnePosterProblem("posters: index.html:", "the video /showroom/demo.webm has no poster")

    def test_a_poster_that_names_no_file_fails_only_as_a_link(self):
        self.with_video('<video src="/showroom/demo.mp4" poster="/showroom/missing.png" controls></video>')
        lines = self.assertFails("/showroom/missing.png leads to no file")
        self.assertEqual([line for line in lines if "posters:" in line], [], lines)

    def test_a_recording_poster_that_names_no_file_fails_only_as_a_link(self):
        self.with_video('<video src="/showroom/demo.mp4" poster="/showroom/missing.webm" controls></video>')
        lines = self.assertFails("/showroom/missing.webm leads to no file")
        self.assertEqual([line for line in lines if "posters:" in line], [], lines)


if __name__ == "__main__":
    unittest.main()

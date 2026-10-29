#!/usr/bin/env python3
"""Tests of check-site.py: a site of its own that passes every check, and, for each check, the same site with one
thing broken, which must fail and name what broke. Every tree is built here, in a temporary directory, never
committed: a committed fixture would break the checks of the repository itself. The Checks workflow
(.github/workflows/checks.yml) runs it.

Usage: check-site-test.py [unittest options]
"""

import os
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
SLUGS = ("index.html", "privacy/index.html", "support/index.html")
MB = 1000 * 1000


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


def footer(language):
    prefix = prefix_of(language)
    return '<footer>\n  <a href="/%sprivacy/">Privacy</a>\n  <a href="/%ssupport/#contact">Support</a>\n</footer>' % (
        prefix,
        prefix,
    )


def page(language, slug, header_html=None, footer_html=None, body=""):
    home = "./" if slug == "index.html" else "../"
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
  <h1 id="title">A page</h1>
  <p><a href="#title">Title</a> <a href="#top">Top</a> <a href="%(home)s">Home</a></p>
  <p><a href="https://github.com/harmflow/harmflow-app">The app</a> <a href="mailto:support@example.com">Mail</a></p>
  <img src="/showroom/poster.png" srcset="/showroom/poster.png 1x, https://harmflow.com/showroom/poster.png 2x" alt="">
  <h2 id="contact">Contact</h2>
  %(body)s
</main>
%(footer)s
</body>
</html>
""" % {
        "language": language,
        "served": served(prefix_of(language), slug),
        "header": header_html if header_html is not None else header(language, slug),
        "home": home,
        "body": body,
        "footer": footer_html if footer_html is not None else footer(language),
    }


NOT_FOUND = """<!doctype html>
<html lang="en-US">
<head><meta charset="utf-8"></head>
<body>
<header><a href="/">HarmFlow</a></header>
<main>
  <p>Page not found. <a href="/">Home</a></p>
  <p lang="pt-BR">Página não encontrada. <a href="/pt-br/">Início</a></p>
  <p lang="es-ES">Página no encontrada. <a href="/es-es/">Inicio</a></p>
</main>
</body>
</html>
"""


def sitemap(rels):
    """A sitemap that lists the pages RELS by their published address."""
    urls = "".join("  <url><loc>https://harmflow.com%s</loc></url>\n" % served("", rel) for rel in rels)
    head = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    return head + urls + "</urlset>\n"


ROBOTS = "User-agent: *\nAllow: /\n\nSitemap: https://harmflow.com/sitemap.xml\n"


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
        self.write("styles/site.css", "body { margin: 0; }\n")
        self.write("showroom/poster.png", "not really a png\n")
        self.write("README.md", "Not a page.\n")

    def write(self, rel, text):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

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

    # The site as it is published for now: en-US pages with no selector, and a 404 page in en-US.
    def test_the_site_in_en_us_only_passes_by_default(self):
        for _, prefix in PREFIXES[1:]:
            shutil.rmtree(os.path.join(self.root, prefix))
        for slug in SLUGS:
            self.write(slug, page("en-US", slug, header_html='<header>\n  <a href="/">HarmFlow</a>\n</header>'))
        translations = NOT_FOUND[NOT_FOUND.index('  <p lang="pt-BR">') : NOT_FOUND.index("</main>")]
        self.write("404.html", NOT_FOUND.replace(translations, ""))
        self.write("sitemap.xml", sitemap(SLUGS))
        self.assertPasses(languages=[])

    def test_a_page_in_a_language_not_published_fails_naming_it(self):
        lines = self.assertFails(
            "unpublished: pt-br/privacy/index.html is a pt-BR page, and the site publishes only en-US",
            "unpublished: es-es/index.html is a es-ES page",
            languages=[],
        )
        self.assertEqual(len([line for line in lines if "unpublished:" in line]), 2 * len(SLUGS), lines)
        self.assertEqual([line for line in lines if "parity:" in line], [], lines)

    def test_an_unknown_language_is_a_usage_error(self):
        rc, _, err = self.check(languages=["--languages", "en-US,fr-FR"])
        self.assertEqual(rc, 2, err)
        self.assertIn("usage:", err)

    # Parity.

    def test_an_en_us_page_with_no_pt_br_version_fails(self):
        os.remove(os.path.join(self.root, "pt-br/privacy/index.html"))
        lines = self.assertFails("parity: pt-br/privacy/index.html is missing")
        self.assertEqual(len([line for line in lines if "parity:" in line]), 1, lines)

    def test_an_en_us_page_with_no_es_es_version_fails(self):
        self.write("showroom/index.html", page("en-US", "showroom/index.html"))
        self.write("pt-br/showroom/index.html", page("pt-BR", "showroom/index.html"))
        self.assertFails("parity: es-es/showroom/index.html is missing")

    def test_a_translated_page_with_no_en_us_version_fails(self):
        self.write("pt-br/showroom/index.html", page("pt-BR", "showroom/index.html"))
        self.write("es-es/showroom/index.html", page("es-ES", "showroom/index.html"))
        self.assertFails("parity: showroom/index.html is missing")

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

    def test_a_selector_that_leads_to_another_page_fails(self):
        wrong = header("es-ES", "privacy/index.html").replace("/pt-br/privacy/", "/pt-br/support/")
        self.write("es-es/privacy/index.html", page("es-ES", "privacy/index.html", header_html=wrong))
        self.assertFails("shared blocks: es-es/privacy/index.html: its header differs")

    def test_two_versions_with_no_majority_name_every_page(self):
        for slug in SLUGS[1:]:
            self.write(slug, page("en-US", slug, footer_html="<footer>Another footer</footer>"))
        self.write("about/index.html", page("en-US", "about/index.html"))
        self.write("pt-br/about/index.html", page("pt-BR", "about/index.html"))
        self.write("es-es/about/index.html", page("es-ES", "about/index.html"))
        lines = self.assertFails("no version is shared by most")
        named = sorted(line.split(": ")[2] for line in lines if "shared blocks:" in line)
        self.assertEqual(named, ["about/index.html", "index.html", "privacy/index.html", "support/index.html"])

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


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Tests of check-consent.py: the site itself, which must pass, and, for each check, a copy of it with one thing broken,
which must fail and name what broke. Every copy is made here, in a temporary directory, never committed. Each break is
a replacement in the site's own files, and a test whose text is no longer there fails rather than passing on an
unbroken copy. The Checks workflow (.github/workflows/checks.yml) runs it. Without Playwright, every test is skipped.

Usage: check-consent-test.py [unittest options]
"""

import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "check-consent.py")
SITE = os.path.join(os.path.dirname(os.path.dirname(HERE)), "site")
CONSENT = "scripts/consent.js"

HAS_PLAYWRIGHT = importlib.util.find_spec("playwright") is not None


@unittest.skipUnless(HAS_PLAYWRIGHT, "Playwright for Python is not installed")
class CheckConsentTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = os.path.join(self.tmp, "site")
        shutil.copytree(SITE, self.root)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def replace(self, rel, old, new):
        path = os.path.join(self.root, rel)
        with open(path, encoding="utf-8") as f:
            text = f.read()
        self.assertIn(old, text, "the text this test breaks is no longer in %s" % rel)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text.replace(old, new, 1))

    def run_check(self):
        return subprocess.run(
            [sys.executable, SCRIPT, self.root], capture_output=True, text=True, timeout=600
        )

    def assertFailsNaming(self, *needles):
        result = self.run_check()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        # A crash exits 1 too: the check must name the problem, not stop at it.
        self.assertNotIn("Traceback", result.stderr)
        for needle in needles:
            self.assertIn(needle, result.stderr)

    def test_the_site_passes(self):
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("check-consent: ok", result.stdout)

    def test_a_tag_loaded_before_consent_fails(self):
        self.replace(CONSENT, "  function init() {\n", "  function init() {\n    startAnalytics();\n")
        self.assertFailsNaming("before consent: / requests https://www.googletagmanager.com/gtag/js")

    def test_a_banner_that_shows_again_after_a_choice_fails(self):
        self.replace(CONSENT, "return window.localStorage.getItem(STORAGE_KEY);", "return null;")
        self.assertFailsNaming("shows the banner again after a reload, once rejected")

    def test_an_accept_that_stands_out_fails(self):
        self.replace(
            CONSENT,
            'button.className = "consent-button";',
            'button.className = "consent-button" + (option[0] === GRANTED ? " primary" : "");',
        )
        self.assertFailsNaming("Accept and Reject differ in prominence")

    def test_an_event_the_site_does_not_measure_fails(self):
        self.replace(CONSENT, 'gtag("js", new Date());', 'gtag("js", new Date());\n    gtag("event", "scroll");')
        self.assertFailsNaming('sends ["event", "scroll"], which the site does not measure')

    def test_google_signals_left_on_fails(self):
        self.replace(CONSENT, "allow_google_signals: false,", "")
        self.assertFailsNaming("without turning Google signals off")

    def test_a_404_visit_not_measured_fails(self):
        self.replace("404.html", '<body data-page="not-found">', "<body>")
        self.assertFailsNaming("the 404 page, at /no-such-page/, sends no page_not_found event")

    def test_cookies_left_after_withdrawing_fail(self):
        self.replace(CONSENT, "    removeAnalyticsCookies();\n    window.location.reload();", "    window.location.reload();")
        self.assertFailsNaming("withdraw: the analytics cookie _ga remains after withdrawing")

    def test_cookies_left_on_the_registrable_domain_after_withdrawing_fail(self):
        self.replace(CONSENT, 'var domains = ["", host, "." + host];', 'var domains = [""];')
        self.assertFailsNaming("withdraw: the analytics cookie _ga remains after withdrawing")

    def test_a_footer_without_the_link_fails(self):
        self.replace(
            "support/index.html", '<li><a href="/privacy/#withdraw" data-consent-choice>Analytics choice</a></li>', ""
        )
        self.assertFailsNaming("withdraw: /support/ has no footer link that reopens the choice")

    def test_content_that_needs_javascript_fails(self):
        self.replace("privacy/index.html", '<main id="content">', '<main id="content" hidden>')
        self.assertFailsNaming("without JavaScript: /privacy/ shows no content")


if __name__ == "__main__":
    unittest.main()

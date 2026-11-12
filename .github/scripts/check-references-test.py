#!/usr/bin/env python3
"""Tests of check-references.py: a repository of its own that passes every rule, and, for each rule, the same
repository with one thing that breaks it, in a file, a commit message, or a pull request's title or body, which must
fail with the rule's label and never print what it matched. Every repository is built here, in a temporary directory,
never committed. The text that breaks a rule is put together when the test runs, so this file breaks none, and the
private patterns are made up for the test: no file of this repository holds a real one, or a copy of what one matches.
The References workflow (.github/workflows/references.yml) runs it before the check.

Usage: check-references-test.py [unittest options]
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "check-references.py")
REPOSITORY_ROOT = os.path.dirname(os.path.dirname(HERE))

# The variables the check reads, which a test sets itself and never inherits from the job that runs it.
CHECK_VARIABLES = ("PRIVATE_REFERENCE_PATTERNS", "PRIVATE_RULES", "PR_TITLE", "PR_BODY", "GITHUB_STEP_SUMMARY")

# A repository of the organization that does not exist, written in each of the three forms, and an address on a domain
# reserved for examples. Each is put together here, so this file holds none of them.
ORGANIZATION = "harmflow"
UNKNOWN = "nonesuch"
BARE_NAME = ORGANIZATION + "-" + UNKNOWN
SLASHED_NAME = ORGANIZATION + "/" + BARE_NAME
ADDRESS = "https://github.com/" + ORGANIZATION + "/" + UNKNOWN
E_MAIL = "jane.doe" + "@" + "example.org"

# The site's measurement ID, the one identifier of Google's tags the check allows, and made-up identifiers of each form
# it does not, put together here so that this file holds none of them.
MEASUREMENT_ID = "G-X0TY5Z9VFR"
OTHER_MEASUREMENT_ID = "G" + "-" + "Q1W2E3R4T5"
TAG_ID = "GT" + "-" + "K7L8M9N0"
ADS_ID = "AW" + "-" + "123456789"
FLOODLIGHT_ID = "DC" + "-" + "7654321"
UNIVERSAL_ANALYTICS_ID = "UA" + "-" + "12345678" + "-" + "1"
CONTAINER_ID = "GTM" + "-" + "ABC1234"
PUBLISHER_ID = "ca" + "-pub-" + "1234567890123456"

# Prose with words that only resemble a prefix: lower case after it, too short, or inside a longer word.
LOOKALIKES = """A G-rated film, a DC-area office, and a GT-class car.
The UA-style team flew a DC-3 to the G-7 and back.
A ca-pub-crawl, the GTM-like setup, BIG-ABCDEF12, and SG-12345678.
"""

# Made-up private patterns, which resemble no real identifier. The second line is blank, so the third pattern is
# "private pattern 3".
PATTERNS = "wombat\n\nquokka-?burrow\n"
FIRST_MATCH = "a wombat"
THIRD_MATCH = "quokkaburrow"

# A tree that passes every rule: the public repositories in each form, the organization before a word that is no
# repository, the addresses allowed, and a high-density image's name.
CLEAN = """# A page

See https://github.com/harmflow/harmflow-app, https://github.com/harmflow/.github/blob/main/SECURITY.md,
harmflow/harmflow-site, harmflow/.github, and a clone of harmflow-app.git in ~/src/harmflow-site.

apiVersion: harmflow/v1alpha1
<a href="https://apps.apple.com/app/harmflow/id1">Get it</a>

Write to hello@harmflow.com. Trailers: noreply@github.com, 49699333+dependabot[bot]@users.noreply.github.com.
<img src="/poster.png" srcset="/poster@2x.png 2x" alt="">
"""


class CheckReferencesTest(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.mkdtemp(prefix="check-references-test.")
        self.addCleanup(shutil.rmtree, self.scratch)
        self.root = os.path.join(self.scratch, "repo")
        os.makedirs(self.root)
        self.git("init", "-q", "-b", "main")
        self.write("README.md", CLEAN)
        self.base = self.commit("docs: add the readme")
        self.patterns = os.path.join(self.scratch, "patterns.txt")
        with open(self.patterns, "w", encoding="utf-8") as f:
            f.write(PATTERNS)

    def git(self, *args):
        env = dict(os.environ)
        env.update(
            GIT_CONFIG_GLOBAL=os.devnull,
            GIT_CONFIG_NOSYSTEM="1",
            GIT_AUTHOR_NAME="Test",
            GIT_AUTHOR_EMAIL="test@harmflow.com",
            GIT_COMMITTER_NAME="Test",
            GIT_COMMITTER_EMAIL="test@harmflow.com",
        )
        result = subprocess.run(
            ["git", "-C", self.root, "-c", "commit.gpgsign=false"] + list(args),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            env=env,
            check=True,
        )
        return result.stdout.strip()

    def write(self, rel, text, track=True):
        """Writes TEXT to REL and, with TRACK, stages it, as the check reads only what git tracks."""
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        mode = "wb" if isinstance(text, bytes) else "w"
        with open(path, mode) as f:
            f.write(text)
        if track:
            self.git("add", rel)

    def commit(self, message):
        self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "-m", message)
        return self.git("rev-parse", "HEAD")

    def check(self, *args, **variables):
        """Runs the check on the test's repository, with ARGS and the check's VARIABLES alone of its own."""
        env = dict((k, v) for k, v in os.environ.items() if k not in CHECK_VARIABLES)
        env.update(variables)
        result = subprocess.run(
            [sys.executable, SCRIPT] + list(args) + [self.root],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            env=env,
        )
        return result.returncode, result.stdout + result.stderr

    def assertPasses(self, *args, **variables):
        rc, out = self.check("--patterns", self.patterns, *args, **variables)
        self.assertEqual(rc, 0, out)
        self.assertIn("No finding", out)
        return out

    def assertFails(self, finding, hidden, *args, **variables):
        """The check fails naming FINDING, a place and a label, and its output holds none of HIDDEN."""
        rc, out = self.check("--patterns", self.patterns, *args, **variables)
        self.assertEqual(rc, 1, out)
        self.assertIn(finding, out)
        for text in hidden:
            self.assertNotIn(text, out)
        return out

    def test_a_clean_repository_passes(self):
        self.assertPasses()

    def test_a_private_repository_by_its_slashed_name_fails(self):
        self.write("site/index.html", "<p>One</p>\n<p>Two</p>\n<p>%s</p>\n" % SLASHED_NAME)
        self.assertFails("site/index.html:3: repository", [UNKNOWN])

    def test_a_private_repository_by_its_address_fails(self):
        self.write("notes.md", "%s/issues\n" % ADDRESS)
        self.assertFails("notes.md:1: repository", [UNKNOWN])

    def test_a_private_repository_by_its_bare_name_fails(self):
        self.write("scripts/run.sh", "#!/bin/sh\ncd ~/src/%s\n" % BARE_NAME)
        self.assertFails("scripts/run.sh:2: repository", [UNKNOWN])

    def test_an_e_mail_address_outside_the_allowed_domains_fails(self):
        self.write("notes.md", "Text.\nWrite to %s.\n" % E_MAIL)
        self.assertFails("notes.md:2: e-mail", [E_MAIL, "jane.doe"])

    def test_the_site_measurement_id_alone_passes(self):
        self.write("site/scripts/consent.js", '(function () {\n  var MEASUREMENT_ID = "%s";\n})();\n' % MEASUREMENT_ID)
        self.write("notes.md", LOOKALIKES)
        self.assertPasses()

    def test_a_second_measurement_id_in_a_page_fails(self):
        self.write("site/scripts/consent.js", 'var MEASUREMENT_ID = "%s";\n' % MEASUREMENT_ID)
        self.write("site/index.html", "<p>One</p>\n<p data-id=\"%s\">Two</p>\n" % OTHER_MEASUREMENT_ID)
        out = self.assertFails("site/index.html:2: account identifier", [OTHER_MEASUREMENT_ID])
        self.assertNotIn("consent.js", out)

    def test_a_tag_manager_container_in_a_script_fails(self):
        self.write("site/scripts/tags.js", "// Tags.\nvar id = '%s';\n" % CONTAINER_ID)
        self.assertFails("site/scripts/tags.js:2: account identifier", [CONTAINER_ID])

    def test_each_form_of_identifier_fails(self):
        for identifier in (TAG_ID, ADS_ID, FLOODLIGHT_ID, UNIVERSAL_ANALYTICS_ID, PUBLISHER_ID):
            with self.subTest(identifier=identifier):
                self.write("notes.md", "Text.\nThe tag (%s) here.\n" % identifier)
                self.assertFails("notes.md:2: account identifier", [identifier])

    def test_an_ads_id_in_a_commit_message_fails(self):
        self.write("a.md", "One.\n")
        head = self.commit("feat: add a\n\nConverts with %s." % ADS_ID)
        self.assertFails(
            "commit %s, line 3: account identifier" % head[:12], [ADS_ID], "--base", self.base, "--head", head
        )

    def test_an_ads_id_in_the_pull_request_body_fails(self):
        body = "## Summary\nOne.\nConverts with %s.\n" % ADS_ID
        self.assertFails(
            "pull request body, line 3: account identifier", [ADS_ID], PR_TITLE="feat: a title", PR_BODY=body
        )

    def test_a_private_pattern_fails_by_its_line_in_the_list(self):
        self.write("site/page.html", "<p>The %s.</p>\n" % THIRD_MATCH)
        out = self.assertFails("site/page.html:1: private pattern 3", [THIRD_MATCH, "quokka", "burrow"])
        self.assertNotIn("private pattern 1", out)

    def test_a_commit_message_from_the_base_to_the_head_fails(self):
        self.write("a.md", "One.\n")
        self.commit("docs: add a\n\nMentions %s." % FIRST_MATCH)
        self.write("b.md", "Two.\n")
        head = self.commit("docs: add b\n\nWritten with\n%s on the line." % E_MAIL)
        out = self.assertFails(
            "commit %s, line 4: e-mail" % head[:12], [E_MAIL, "wombat"], "--base", self.base, "--head", head
        )
        self.assertIn("line 3: private pattern 1", out)

    def test_a_commit_message_before_the_base_is_not_read(self):
        self.write("a.md", "One.\n")
        base = self.commit("docs: add a\n\n%s" % E_MAIL)
        self.write("b.md", "Two.\n")
        head = self.commit("docs: add b")
        out = self.assertPasses("--base", base, "--head", head)
        self.assertIn("1 commit message.", out)

    def test_the_pull_request_title_fails(self):
        self.assertFails("pull request title: repository", [UNKNOWN], PR_TITLE="docs: link " + SLASHED_NAME)

    def test_the_pull_request_body_fails_by_its_line(self):
        body = "## Summary\r\nSee %s.\r\nAnd %s.\r\n" % (FIRST_MATCH, E_MAIL)
        out = self.assertFails(
            "pull request body, line 2: private pattern 1", ["wombat", E_MAIL], PR_TITLE="docs: a title", PR_BODY=body
        )
        self.assertIn("pull request body, line 3: e-mail", out)

    def test_a_binary_file_is_skipped(self):
        self.write("site/image.png", b"\x89PNG\r\n\x1a\n\0\0" + E_MAIL.encode("ascii") + b"\n")
        self.commit("feat: add an image")
        self.assertPasses()

    def test_an_untracked_file_is_not_read(self):
        self.write("scratch.md", "%s\n" % E_MAIL, track=False)
        self.assertPasses()
        self.git("add", "scratch.md")
        self.assertFails("scratch.md:1: e-mail", [E_MAIL])

    def test_the_patterns_are_read_from_the_environment_without_a_file(self):
        self.write("notes.md", "%s\n" % FIRST_MATCH)
        rc, out = self.check(PRIVATE_REFERENCE_PATTERNS=PATTERNS)
        self.assertEqual(rc, 1, out)
        self.assertIn("notes.md:1: private pattern 1", out)
        self.assertNotIn("wombat", out)

    def test_a_run_that_requires_the_patterns_fails_without_them(self):
        rc, out = self.check(PRIVATE_RULES="required")
        self.assertEqual(rc, 1, out)
        self.assertIn("PRIVATE_REFERENCE_PATTERNS secret", out)
        rc, out = self.check(PRIVATE_RULES="required", PRIVATE_REFERENCE_PATTERNS="\n")
        self.assertEqual(rc, 1, out)

    def test_a_run_that_cannot_read_the_patterns_by_design_skips_them_and_says_so(self):
        summary = os.path.join(self.scratch, "summary.md")
        rc, out = self.check(PRIVATE_RULES="optional", GITHUB_STEP_SUMMARY=summary)
        self.assertEqual(rc, 0, out)
        with open(summary, encoding="utf-8") as f:
            self.assertIn("The private rules were skipped", f.read())
        self.write("notes.md", "%s\n" % E_MAIL)
        rc, out = self.check(PRIVATE_RULES="optional", GITHUB_STEP_SUMMARY=summary)
        self.assertEqual(rc, 1, out)
        self.assertIn("notes.md:1: e-mail", out)

    def test_a_local_run_without_patterns_says_it_skipped_them(self):
        rc, out = self.check()
        self.assertEqual(rc, 0, out)
        self.assertIn("Skipped the private rules", out)

    def test_an_invalid_pattern_is_named_by_its_line_alone(self):
        with open(self.patterns, "w", encoding="utf-8") as f:
            f.write("wombat\nquokka[burrow\n")
        rc, out = self.check("--patterns", self.patterns)
        self.assertEqual(rc, 2, out)
        self.assertIn("private pattern 2 is not a valid regular expression", out)
        self.assertNotIn("quokka", out)

    def test_the_measurement_id_allowed_is_the_one_the_consent_carries(self):
        with open(os.path.join(REPOSITORY_ROOT, "site", "scripts", "consent.js"), encoding="utf-8") as f:
            self.assertIn('MEASUREMENT_ID = "%s"' % MEASUREMENT_ID, f.read())

    def test_this_repository_passes_the_public_rules(self):
        env = dict((k, v) for k, v in os.environ.items() if k not in CHECK_VARIABLES)
        result = subprocess.run(
            [sys.executable, SCRIPT, REPOSITORY_ROOT],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            env=env,
        )
        self.assertEqual(result.returncode, 0, result.stdout)


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Tests of check-samples.py: reference pages of its own whose samples are valid, which must pass, and, for each
failure, a page with one broken sample, which must fail and name the page, the sample, and what is wrong. Every page is
built here, in a temporary directory, never committed, and validated against a task schema the test supplies, so the
tests need no network; the workflow's step that checks site/ fetches the schema the page pins. The Checks workflow
(.github/workflows/checks.yml) runs it. Without PyYAML and jsonschema, every test that needs them is skipped.

Usage: check-samples-test.py [unittest options]
"""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "check-samples.py")
SITE = os.path.join(os.path.dirname(os.path.dirname(HERE)), "site")
TASK_FILE = "docs/reference/task-file/index.html"

HAS_DEPENDENCIES = all(importlib.util.find_spec(name) is not None for name in ("yaml", "jsonschema"))

# A commit the pages of the tests pin, which no test fetches.
PINNED = "0123456789abcdef0123456789abcdef01234567"
SCHEMA_LINK = "https://github.com/harmflow/harmflow-app/blob/%s/contracts/schemas/task.schema.json"

# The task schema the tests supply: the top-level keys, a metadata id and name, a spec type, and an integer timeout.
SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": False,
    "required": ["apiVersion", "kind", "metadata", "spec"],
    "properties": {
        "apiVersion": {"const": "harmflow/v1alpha1"},
        "kind": {"const": "Task"},
        "metadata": {
            "type": "object",
            "required": ["id", "name"],
            "properties": {"id": {"type": "string"}, "name": {"type": "string"}},
        },
        "spec": {
            "type": "object",
            "required": ["type"],
            "properties": {
                "type": {"enum": ["general", "script"]},
                "execution": {
                    "type": "object",
                    "properties": {"timeoutMinutes": {"type": "integer"}},
                },
            },
        },
    },
}

GENERAL = """apiVersion: harmflow/v1alpha1
kind: Task
metadata:
  id: weekly-notes
  name: Weekly notes
spec:
  type: general
  execution:
    timeoutMinutes: 30"""

SCRIPT_TASK = """apiVersion: harmflow/v1alpha1
kind: Task
metadata:
  id: nightly-fetch
  name: Nightly fetch
spec:
  type: script"""


def reference_page(*sections, link=SCHEMA_LINK % PINNED):
    """A reference page: an h1, a paragraph that links to the task schema unless link is None, and each section, a
    heading and the text of a <pre><code> block under it."""
    parts = ['<!doctype html>\n<html lang="en">\n<body>\n<main>\n<h1>The task file</h1>']
    if link is not None:
        parts.append('<p>The schema is <a href="%s"><code>task.schema.json</code></a>.</p>' % link)
    for heading, code in sections:
        parts.append("<h2>%s</h2>\n<pre><code>%s</code></pre>" % (heading, code))
    parts.append("</main>\n</body>\n</html>\n")
    return "\n".join(parts)


def load_check():
    spec = importlib.util.spec_from_file_location("check_samples", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@unittest.skipUnless(HAS_DEPENDENCIES, "PyYAML and jsonschema are not installed")
class CheckSamplesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = os.path.join(self.tmp, "site")
        self.schema = os.path.join(self.tmp, "task.schema.json")
        with open(self.schema, "w", encoding="utf-8") as f:
            json.dump(SCHEMA, f)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def write(self, rel, text):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

    def run_check(self):
        return subprocess.run(
            [sys.executable, SCRIPT, "--schema", self.schema, self.root],
            capture_output=True,
            text=True,
        )

    def assertPasses(self, samples):
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ok: %d task file samples" % samples, result.stdout)

    def assertFailsNaming(self, *needles):
        result = self.run_check()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        for needle in needles:
            self.assertIn(needle, result.stderr)
        return result.stderr

    def test_valid_samples_pass(self):
        self.write(TASK_FILE, reference_page(("An example", GENERAL), ("The script section", SCRIPT_TASK)))
        self.assertPasses(2)

    def test_a_missing_required_key_fails(self):
        broken = GENERAL.replace("kind: Task\n", "")
        self.write(TASK_FILE, reference_page(("An example", broken), ("The script section", SCRIPT_TASK)))
        stderr = self.assertFailsNaming(
            TASK_FILE + ': sample 1, under "An example": the task schema rejects it at the document\'s root:',
            "'kind' is a required property",
        )
        self.assertNotIn("sample 2", stderr)

    def test_a_field_of_the_wrong_type_fails(self):
        broken = GENERAL.replace("timeoutMinutes: 30", "timeoutMinutes: thirty")
        self.write(TASK_FILE, reference_page(("The script section", SCRIPT_TASK), ("An example", broken)))
        self.assertFailsNaming(
            TASK_FILE + ': sample 2, under "An example": the task schema rejects it at spec.execution.timeoutMinutes:',
            "'thirty' is not of type 'integer'",
        )

    def test_text_that_is_not_yaml_fails(self):
        broken = GENERAL.replace("  name: Weekly notes", "  name: [Weekly notes")
        self.write(TASK_FILE, reference_page(("An example", broken)))
        self.assertFailsNaming(TASK_FILE + ': sample 1, under "An example": is not YAML at line ')

    def test_a_sample_is_found_by_its_text(self):
        # A block that does not start with the task file's first key is no sample, nor is a <code> outside <pre>; a
        # sample on another reference page, under any heading, is read with no change to the rule.
        page = reference_page(("An example", GENERAL), ("A request", '{"enabled": false}'))
        page = page.replace("</main>", "<p><code>apiVersion: harmflow/v1alpha1</code></p>\n</main>")
        self.write(TASK_FILE, page)
        other = SCRIPT_TASK.replace("type: script", "type: nightly")
        self.write("docs/reference/other/index.html", reference_page(("Another page", other)))
        self.write("docs/guide/index.html", reference_page(("Not the reference", "apiVersion: harmflow/v1alpha1\n")))
        self.assertFailsNaming(
            'docs/reference/other/index.html: sample 1, under "Another page": the task schema rejects it at spec.type:'
        )
        self.write("docs/reference/other/index.html", reference_page(("Another page", SCRIPT_TASK)))
        self.assertPasses(2)

    def test_the_text_is_read_as_the_page_shows_it(self):
        # Character references are the text the reader copies, and a value YAML 1.1 would read as a boolean or a date
        # stays text, as the daemon reads it.
        sample = GENERAL.replace("Weekly notes", "&quot;The week&#x27;s notes&quot;").replace("weekly-notes", "no")
        dated = SCRIPT_TASK.replace("Nightly fetch", "2026-01-01")
        self.write(TASK_FILE, reference_page(("An example", sample), ("A dated one", dated)))
        self.assertPasses(2)

    def test_the_schema_is_the_one_the_page_pins(self):
        check = load_check()
        fetched = []

        def fetch(sha):
            fetched.append(sha)
            return SCHEMA

        self.write(TASK_FILE, reference_page(("An example", GENERAL)))
        self.write("docs/reference/other/index.html", reference_page(("Another page", SCRIPT_TASK)))
        self.assertEqual(check.check(self.root, fetch=fetch), ([], 2))
        self.assertEqual(fetched, [PINNED])

        self.write("docs/reference/other/index.html", reference_page(("Another page", SCRIPT_TASK), link=None))
        problems, _ = check.check(self.root, fetch=fetch)
        self.assertEqual(
            problems,
            ["docs/reference/other/index.html: it holds task file samples but no link to the task schema at a pinned "
             "commit"],
        )

        moving = SCHEMA_LINK % "main"
        self.write("docs/reference/other/index.html", reference_page(("Another page", SCRIPT_TASK), link=moving))
        problems, _ = check.check(self.root, fetch=fetch)
        self.assertEqual(
            problems,
            ["docs/reference/other/index.html: its link to the task schema pins no full commit SHA: " + moving],
        )

        def unreachable(sha):
            raise OSError("the schema at %s cannot be fetched" % sha)

        self.write("docs/reference/other/index.html", reference_page(("Another page", SCRIPT_TASK)))
        problems, _ = check.check(self.root, fetch=unreachable)
        self.assertEqual(len(problems), 2)
        unread = ": the task schema cannot be read: the schema at %s cannot be fetched" % PINNED
        self.assertEqual(problems, ["docs/reference/other/index.html" + unread, TASK_FILE + unread])


class ReferencePageTest(unittest.TestCase):
    """What the check reads on the repository's own task file page, without fetching the schema it pins."""

    def test_the_task_file_page_holds_its_samples_and_its_pin(self):
        check = load_check()
        page = check.read_page(SITE, TASK_FILE)
        found = check.samples(page)
        self.assertGreaterEqual(len(found), 2)
        self.assertEqual([heading for _, heading, _ in found[:2]], ["An example", "The script section"])
        sha, problems = check.pinned_schema(TASK_FILE, page)
        self.assertEqual(problems, [])
        self.assertRegex(sha, "^[0-9a-f]{40}$")


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Tests of check-schema-coverage.py: a task file page and a harnesses page that name everything, which must pass, and,
for each failure, pages that leave something out, which must fail and name the page and what it leaves out. Every page
is built here, in a temporary directory, never committed, and read against a task schema the test supplies, so the
tests need no network; the workflow's step that checks site/ fetches the schema the task file page pins. The Checks
workflow (.github/workflows/checks.yml) runs it.

Usage: check-schema-coverage-test.py [unittest options]
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
SCRIPT = os.path.join(HERE, "check-schema-coverage.py")
SITE = os.path.join(os.path.dirname(os.path.dirname(HERE)), "site")
INDEX = "docs/reference/index.html"
TASK_FILE = "docs/reference/task-file/index.html"
HARNESSES = "docs/reference/harnesses/index.html"

# A commit the pages of the tests pin, which no test fetches.
PINNED = "0123456789abcdef0123456789abcdef01234567"
SCHEMA_LINK = "https://github.com/harmflow/harmflow-app/blob/%s/contracts/schemas/task.schema.json"

# The task schema the tests supply. Its property names are apiVersion, kind, metadata, spec, and id inline, and, in
# $defs, harness and its preferred, fallback, candidates, and provider; maxSwitches only under an if; and notifications
# and events under allOf. The names under $defs, the enum's values, and a const's object are no property names.
SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
        "apiVersion": {"const": "harmflow/v1alpha1"},
        "kind": {"const": "Task"},
        "metadata": {"type": "object", "properties": {"id": {"type": "string"}}},
        "spec": {
            "type": "object",
            "properties": {"harness": {"$ref": "#/$defs/harness"}},
            "allOf": [{"properties": {"notifications": {"properties": {"events": {"type": "array"}}}}}],
        },
    },
    "$defs": {
        "harnessProvider": {"type": "string", "enum": ["claude-code", "codex"]},
        "harness": {
            "type": "object",
            "properties": {
                "preferred": {"$ref": "#/$defs/harnessProvider"},
                "fallback": {
                    "type": "object",
                    "properties": {
                        "candidates": {
                            "type": "array",
                            "items": {"properties": {"provider": {"$ref": "#/$defs/harnessProvider"}}},
                        },
                    },
                    "if": {"required": ["candidates"]},
                    "then": {"properties": {"maxSwitches": {"type": "integer"}}},
                },
            },
            "default": {"properties": {"notAField": True}},
        },
    },
}

FIELDS = [
    "apiVersion", "candidates", "events", "fallback", "harness", "id", "kind", "maxSwitches", "metadata",
    "notifications", "preferred", "provider", "spec",
]

# The shared header and footer, which hold text of their own, a code element and a heading among it.
HEADER = '<header><h2>maxSwitches</h2><a href="/docs/reference/">Reference</a></header>'
FOOTER = "<footer><p><code>codex</code> and <code>provider</code></p></footer>"

# A task file page's main that names every field: in code elements, dotted or alone; in headings; and in a sample's
# <pre><code> block.
TASK_FILE_MAIN = """<h1>The task file</h1>
<p>The schema is <a href="%(link)s"><code>task.schema.json</code></a>.</p>
<h2>The top-level keys</h2>
<p><code>apiVersion</code>, <code>kind</code>, <code>metadata.id</code>, and <code>spec</code>.</p>
<h3 id="notifications">notifications</h3>
<p>Its <code>events</code> list.</p>
<h3 id="harness">harness</h3>
<ul>
  <li><code>preferred</code>, then <code>fallback.candidates[0].provider</code>.</li>
  <li>At most <code>fallback.maxSwitches</code> switches.</li>
</ul>
<h2>An example</h2>
<pre><code>apiVersion: harmflow/v1alpha1
kind: Task</code></pre>"""

# A harnesses page's main that names each harness as the whole text of a code element.
HARNESSES_MAIN = """<h1>The harnesses</h1>
<p>Claude Code (<code>claude-code</code>) or Codex (<code> codex </code>).</p>"""


def page(main_html):
    """A page: the shared header, the main, and the shared footer."""
    return '<!doctype html>\n<html lang="en">\n<body>\n%s\n<main id="content">\n%s\n</main>\n%s\n</body>\n</html>\n' % (
        HEADER,
        main_html,
        FOOTER,
    )


def task_file_page(link=SCHEMA_LINK % PINNED, main_html=TASK_FILE_MAIN):
    return page(main_html % {"link": link})


def load_check():
    spec = importlib.util.spec_from_file_location("check_schema_coverage", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CheckSchemaCoverageTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = os.path.join(self.tmp, "site")
        self.schema = os.path.join(self.tmp, "task.schema.json")
        with open(self.schema, "w", encoding="utf-8") as f:
            json.dump(SCHEMA, f)
        self.write(INDEX, page("<h1>The technical reference</h1>"))
        self.write(TASK_FILE, task_file_page())
        self.write(HARNESSES, page(HARNESSES_MAIN))

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

    def assertPasses(self):
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ok: the task file page names the task schema's %d fields" % len(FIELDS), result.stdout)
        self.assertIn("the harnesses page its 2 harnesses", result.stdout)

    def assertFailsNaming(self, *needles):
        result = self.run_check()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        for needle in needles:
            self.assertIn(needle, result.stderr)
        return result.stderr

    def test_pages_that_name_everything_pass(self):
        self.assertPasses()

    def test_every_property_name_is_collected(self):
        self.assertEqual(sorted(load_check().property_names(SCHEMA)), FIELDS)

    def test_a_task_file_page_that_lacks_a_nested_field_fails(self):
        self.write(TASK_FILE, task_file_page(main_html=TASK_FILE_MAIN.replace("fallback.maxSwitches", "fallback")))
        stderr = self.assertFailsNaming(TASK_FILE + ": its main does not name the task schema's field maxSwitches")
        self.assertIn("1 problems", stderr)

    def test_a_field_in_prose_only_is_not_named(self):
        # A field the page writes only in a paragraph's text, outside any code element or heading, is not named; nor
        # is one that is only part of a token, as `events` is of `eventsList`.
        main_html = TASK_FILE_MAIN.replace("Its <code>events</code> list.", "Its events list, <code>eventsList</code>.")
        self.write(TASK_FILE, task_file_page(main_html=main_html))
        self.assertFailsNaming(TASK_FILE + ": its main does not name the task schema's field events")

    def test_a_field_named_by_a_heading_alone_is_named(self):
        main_html = TASK_FILE_MAIN.replace("<code>metadata.id</code>", "<code>metadata</code>")
        main_html = main_html.replace("<h2>An example</h2>", "<h4>The <code>x</code> of each id</h4>")
        self.write(TASK_FILE, task_file_page(main_html=main_html))
        self.assertPasses()

    def test_a_harnesses_page_that_lacks_a_harness_fails(self):
        self.write(HARNESSES, page(HARNESSES_MAIN.replace("<code> codex </code>", "<code>codex exec</code>")))
        stderr = self.assertFailsNaming(HARNESSES + ": no <code> of its main reads the harness codex")
        self.assertNotIn("harness claude-code", stderr)

    def test_a_harness_in_prose_only_is_not_named(self):
        self.write(HARNESSES, page(HARNESSES_MAIN.replace("(<code>claude-code</code>)", "(claude-code)")))
        self.assertFailsNaming(HARNESSES + ": no <code> of its main reads the harness claude-code")

    def test_only_the_main_is_read(self):
        # The header names maxSwitches in a heading and the footer codex and provider in code elements: none counts.
        main_html = TASK_FILE_MAIN.replace("fallback.maxSwitches", "fallback").replace(".provider", "")
        self.write(TASK_FILE, task_file_page(main_html=main_html))
        self.write(HARNESSES, page(HARNESSES_MAIN.replace("<code> codex </code>", "")))
        self.assertFailsNaming(
            TASK_FILE + ": its main does not name the task schema's field maxSwitches",
            TASK_FILE + ": its main does not name the task schema's field provider",
            HARNESSES + ": no <code> of its main reads the harness codex",
        )

    def test_a_tree_with_no_reference_index_passes(self):
        os.remove(os.path.join(self.root, INDEX))
        self.write(HARNESSES, page("<h1>The harnesses</h1>"))
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_a_schema_with_no_harness_enum_fails(self):
        schema = dict(SCHEMA, **{"$defs": {"harness": SCHEMA["$defs"]["harness"]}})
        with open(self.schema, "w", encoding="utf-8") as f:
            json.dump(schema, f)
        self.assertFailsNaming(HARNESSES + ": the task schema has no harnessProvider enum to read the harnesses from")

    def test_the_schema_is_the_one_the_task_file_page_pins(self):
        check = load_check()
        fetched = []

        def fetch(sha):
            fetched.append(sha)
            return SCHEMA

        self.assertEqual(check.check(self.root, fetch=fetch), ([], (len(FIELDS), 2)))
        self.assertEqual(fetched, [PINNED])

        self.write(TASK_FILE, task_file_page(link="/docs/reference/"))
        problems, _ = check.check(self.root, fetch=fetch)
        self.assertEqual(problems, [TASK_FILE + ": its main has no link to the task schema at a pinned commit"])

        moving = SCHEMA_LINK % "main"
        self.write(TASK_FILE, task_file_page(link=moving))
        problems, _ = check.check(self.root, fetch=fetch)
        self.assertEqual(problems, [TASK_FILE + ": its link to the task schema pins no full commit SHA: " + moving])

        def unreachable(sha):
            raise OSError("the schema at %s cannot be fetched" % sha)

        self.write(TASK_FILE, task_file_page())
        problems, _ = check.check(self.root, fetch=unreachable)
        self.assertEqual(
            problems, [TASK_FILE + ": the task schema cannot be read: the schema at %s cannot be fetched" % PINNED]
        )


class ReferencePageTest(unittest.TestCase):
    """What the check reads on the repository's own task file page, without fetching the schema it pins."""

    def test_the_task_file_page_pins_the_schema(self):
        check = load_check()
        sha, problems = check.pinned_schema(TASK_FILE, check.read_main(SITE, TASK_FILE))
        self.assertEqual(problems, [])
        self.assertRegex(sha, "^[0-9a-f]{40}$")


if __name__ == "__main__":
    unittest.main()

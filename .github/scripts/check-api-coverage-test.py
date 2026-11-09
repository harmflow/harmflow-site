#!/usr/bin/env python3
"""Tests of check-api-coverage.py: a local API page and a harnesses page that name every operation, each form of naming
one with a test that passes, and an operation named in none of them, or in a form broken, with a test that fails and
names it by its method and path. Every page is built here, in a temporary directory, never committed, and read against
an API description the test supplies, so the tests need no network; the workflow's step that checks site/ fetches the
description the local API page pins. The Checks workflow (.github/workflows/checks.yml) runs it. Without PyYAML, every
test that needs it is skipped.

Usage: check-api-coverage-test.py [unittest options]
"""

import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "check-api-coverage.py")
SITE = os.path.join(os.path.dirname(os.path.dirname(HERE)), "site")
INDEX = "docs/reference/index.html"
LOCAL_API = "docs/reference/local-api/index.html"
HARNESSES = "docs/reference/harnesses/index.html"

HAS_DEPENDENCIES = importlib.util.find_spec("yaml") is not None

# A commit the pages of the tests pin, which no test fetches.
PINNED = "0123456789abcdef0123456789abcdef01234567"
DESCRIPTION_LINK = "https://github.com/harmflow/harmflow-app/blob/%s/contracts/api/openapi.yaml"

# The API description the tests supply: 12 operations. harnessId's enum is given through a reference, at the path
# item's level; templateId has none.
DESCRIPTION = """openapi: 3.1.0
info: { title: A local API, version: v1 }
paths:
  /tasks:
    get: { summary: List tasks }
    post: { summary: Create a task }
  /tasks/{taskId}:
    parameters:
      - { name: taskId, in: path, required: true, schema: { type: string } }
    get: { summary: Get a task }
    put: { summary: Update a task }
    delete: { summary: Delete a task }
  /tasks/{taskId}/run:
    post: { summary: Run it }
  /tasks/{taskId}/enable:
    post: { summary: Enable it }
  /tasks/{taskId}/disable:
    post: { summary: Disable it }
  /harnesses/{harnessId}/sign-in:
    parameters:
      - $ref: "#/components/parameters/HarnessId"
    post: { summary: Sign in }
  /harnesses/{harnessId}/token:
    parameters:
      - $ref: "#/components/parameters/HarnessId"
    put: { summary: Save a token }
    delete: { summary: Remove the token }
  /templates/{templateId}:
    parameters:
      - { name: templateId, in: path, required: true, schema: { type: string } }
    summary: Not an operation
    delete: { summary: Delete a template }
components:
  parameters:
    HarnessId:
      name: harnessId
      in: path
      required: true
      schema: { $ref: "#/components/schemas/HarnessProvider" }
  schemas:
    HarnessProvider: { type: string, enum: [claude-code, codex] }
"""

# The shared header and footer, which hold text of their own, an operation among it.
HEADER = '<header><p><code>DELETE /templates/{templateId}</code></p><a href="/docs/reference/">Reference</a></header>'
FOOTER = "<footer><ul><li><code>GET /tasks</code></li></ul></footer>"

# A local API page's main that names its operations in each form: a method and a path; methods of their own before
# one; a single segment after one.
LOCAL_API_MAIN = """<h1>The local API</h1>
<p>The authority is <a href="%(link)s"><code>contracts/api/openapi.yaml</code></a>.</p>
<ul>
  <li><code>GET /tasks</code> — every task; <code>POST /tasks</code> — create one.</li>
  <li><code>GET</code>, <code>PUT</code>, and <code>DELETE /tasks/{taskId}</code> — read, update, and delete one.</li>
  <li><code>POST /tasks/{taskId}/run</code> — start it; <code>/enable</code> and <code>/disable</code> — enable and
    disable it.</li>
  <li><code>DELETE /templates/{templateId}</code> — delete a template.</li>
</ul>"""

# A harnesses page's main that names its operations with a path parameter given a value its enum allows, or as the
# description writes it.
HARNESSES_MAIN = """<h1>The harnesses</h1>
<p>Sign in from HarmFlow (<code>POST /harnesses/codex/sign-in</code>), save a token
  (<code>PUT /harnesses/{harnessId}/token</code>),
  or remove it (<code>DELETE /harnesses/claude-code/token</code>).</p>"""


def page(main_html):
    """A page: the shared header, the main, and the shared footer."""
    return '<!doctype html>\n<html lang="en">\n<body>\n%s\n<main id="content">\n%s\n</main>\n%s\n</body>\n</html>\n' % (
        HEADER,
        main_html,
        FOOTER,
    )


def local_api_page(main_html=LOCAL_API_MAIN, link=DESCRIPTION_LINK % PINNED):
    return page(main_html % {"link": link})


def load_check():
    spec = importlib.util.spec_from_file_location("check_api_coverage", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@unittest.skipUnless(HAS_DEPENDENCIES, "PyYAML is not installed")
class CheckApiCoverageTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = os.path.join(self.tmp, "site")
        self.description = os.path.join(self.tmp, "openapi.yaml")
        with open(self.description, "w", encoding="utf-8") as f:
            f.write(DESCRIPTION)
        self.write(INDEX, page("<h1>The technical reference</h1>"))
        self.write(LOCAL_API, local_api_page())
        self.write(HARNESSES, page(HARNESSES_MAIN))

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def write(self, rel, text):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

    def write_local_api(self, old, new):
        self.assertIn(old, LOCAL_API_MAIN)
        self.write(LOCAL_API, local_api_page(LOCAL_API_MAIN.replace(old, new)))

    def write_harnesses(self, old, new):
        self.assertIn(old, HARNESSES_MAIN)
        self.write(HARNESSES, page(HARNESSES_MAIN.replace(old, new)))

    def run_check(self):
        return subprocess.run(
            [sys.executable, SCRIPT, "--description", self.description, self.root],
            capture_output=True,
            text=True,
        )

    def assertPasses(self):
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ok: the reference names each of the local API's 12 operations", result.stdout)

    def assertFailsNaming(self, *operations):
        """The check fails, naming exactly these operations."""
        result = self.run_check()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        named = [
            line[len("check-api-coverage: ") :].split(": named nowhere")[0]
            for line in result.stderr.splitlines()
            if ": named nowhere in the main of %s or %s" % (LOCAL_API, HARNESSES) in line
        ]
        self.assertEqual(named, list(operations), result.stderr)

    def test_pages_that_name_every_operation_pass(self):
        self.assertPasses()

    def test_a_method_and_its_path(self):
        self.write_local_api("<code>POST /tasks</code>", "<code>POST /tasks/</code>")
        self.assertFailsNaming("POST /tasks")

    def test_a_path_parameter_given_a_value_of_its_enum(self):
        # codex and claude-code are values of harnessId's enum, {harnessId} the parameter as written; a value outside
        # the enum names nothing, nor does one for a parameter with no enum.
        self.assertPasses()
        self.write_harnesses("/harnesses/codex/sign-in", "/harnesses/gemini/sign-in")
        self.assertFailsNaming("POST /harnesses/{harnessId}/sign-in")
        self.write(HARNESSES, page(HARNESSES_MAIN))
        self.write_local_api("DELETE /templates/{templateId}", "DELETE /templates/hf-weekly")
        self.assertFailsNaming("DELETE /templates/{templateId}")

    def test_methods_of_their_own_before_a_method_and_its_path(self):
        self.write_local_api("<code>PUT</code>, and", "and")
        self.assertFailsNaming("PUT /tasks/{taskId}")

    def test_methods_of_their_own_name_nothing_after_it_or_in_another_block(self):
        # A method of its own after the method and path, or in another list item, names nothing.
        self.write_local_api(
            "<li><code>GET</code>, <code>PUT</code>, and <code>DELETE /tasks/{taskId}</code>",
            "<li><code>GET</code> the list;</li>\n  <li><code>DELETE /tasks/{taskId}</code>, <code>PUT</code>",
        )
        self.assertFailsNaming("GET /tasks/{taskId}", "PUT /tasks/{taskId}")

    def test_methods_of_their_own_name_only_the_next_path(self):
        # GET and PUT name GET and PUT /tasks, the next method and path, and not DELETE /tasks/{taskId}'s path after it.
        self.write_local_api(
            "<code>GET</code>, <code>PUT</code>, and <code>DELETE /tasks/{taskId}</code>",
            "<code>GET</code>, <code>PUT</code>, <code>POST /tasks</code>, and <code>DELETE /tasks/{taskId}</code>",
        )
        self.assertFailsNaming("GET /tasks/{taskId}", "PUT /tasks/{taskId}")

    def test_a_segment_after_a_method_and_its_path(self):
        # /enable and /disable stand for the run path with its last segment replaced, with its method.
        self.assertPasses()
        self.write_local_api("<code>/disable</code>", "<code>disable</code>")
        self.assertFailsNaming("POST /tasks/{taskId}/disable")

    def test_a_segment_names_nothing_before_it_or_in_another_block(self):
        self.write_local_api("— start it; <code>/enable</code>", "— start it.</li>\n  <li><code>/enable</code>")
        self.assertFailsNaming("POST /tasks/{taskId}/enable", "POST /tasks/{taskId}/disable")
        self.write_local_api(
            "<code>POST /tasks/{taskId}/run</code> — start it; <code>/enable</code>",
            "<code>/enable</code>, then <code>POST /tasks/{taskId}/run</code> — start it; <code>/stop</code>",
        )
        self.assertFailsNaming("POST /tasks/{taskId}/enable")

    def test_an_operation_named_nowhere_fails(self):
        self.write_harnesses("or remove it (<code>DELETE /harnesses/claude-code/token</code>)", "")
        self.assertFailsNaming("DELETE /harnesses/{harnessId}/token")

    def test_the_method_counts(self):
        # The path of DELETE /harnesses/{harnessId}/token, with another method, does not name it.
        self.write_harnesses("DELETE /harnesses/claude-code/token", "GET /harnesses/claude-code/token")
        self.assertFailsNaming("DELETE /harnesses/{harnessId}/token")

    def test_only_the_main_is_read(self):
        # The header names DELETE /templates/{templateId} and the footer GET /tasks: neither counts.
        main_html = LOCAL_API_MAIN.replace("<code>GET /tasks</code> — every task; ", "")
        main_html = main_html.replace("<li><code>DELETE /templates/{templateId}</code> — delete a template.</li>", "")
        self.write(LOCAL_API, local_api_page(main_html))
        self.assertFailsNaming("GET /tasks", "DELETE /templates/{templateId}")

    def test_either_page_names_an_operation(self):
        self.write_local_api("<li><code>DELETE /templates/{templateId}</code> — delete a template.</li>", "")
        self.write(HARNESSES, page(HARNESSES_MAIN + "\n<p><code>DELETE /templates/{templateId}</code></p>"))
        self.assertPasses()

    def test_a_tree_with_no_reference_index_passes(self):
        os.remove(os.path.join(self.root, INDEX))
        self.write(LOCAL_API, page("<h1>The local API</h1>"))
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_a_description_that_is_not_yaml_fails(self):
        with open(self.description, "w", encoding="utf-8") as f:
            f.write("paths: [")
        result = self.run_check()
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertIn(LOCAL_API + ": the API description cannot be read: it is not YAML", result.stderr)

    def test_the_description_is_the_one_the_local_api_page_pins(self):
        check = load_check()
        fetched = []

        def fetch(sha):
            fetched.append(sha)
            return DESCRIPTION

        self.assertEqual(check.check(self.root, fetch=fetch), ([], 12))
        self.assertEqual(fetched, [PINNED])

        self.write(LOCAL_API, local_api_page(link="/docs/reference/"))
        problems, _ = check.check(self.root, fetch=fetch)
        self.assertEqual(problems, [LOCAL_API + ": its main has no link to the API description at a pinned commit"])

        moving = DESCRIPTION_LINK % "main"
        self.write(LOCAL_API, local_api_page(link=moving))
        problems, _ = check.check(self.root, fetch=fetch)
        self.assertEqual(problems, [LOCAL_API + ": its link to the API description pins no full commit SHA: " + moving])

        def unreachable(sha):
            raise OSError("the description at %s cannot be fetched" % sha)

        self.write(LOCAL_API, local_api_page())
        problems, _ = check.check(self.root, fetch=unreachable)
        self.assertEqual(
            problems,
            [LOCAL_API + ": the API description cannot be read: the description at %s cannot be fetched" % PINNED],
        )


class ReferencePageTest(unittest.TestCase):
    """What the check reads on the repository's own local API page, without fetching the description it pins."""

    def test_the_local_api_page_pins_the_description(self):
        check = load_check()
        sha, problems = check.pinned_description(LOCAL_API, check.read_main(SITE, LOCAL_API))
        self.assertEqual(problems, [])
        self.assertRegex(sha, "^[0-9a-f]{40}$")


if __name__ == "__main__":
    unittest.main()

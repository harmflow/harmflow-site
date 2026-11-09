#!/usr/bin/env python3
"""Checks that two parts of the technical reference cover their whole subject, measured against the app's task schema
at the commit of harmflow-app that the task file page's link to contracts/schemas/task.schema.json pins:

- the task file page names every property name the schema defines, at every depth — the keys of every `properties`
  object, in `$defs` and inline — each as a token of a code element or a heading (h1 to h6) of its main. A token is a
  run of letters, digits, `_`, and `-`, so `<code>native.enabled</code>` names `native` and `enabled`, and the
  samples' <pre><code> blocks are code elements too;
- the harnesses page names each value of the schema's `harnessProvider` enum as the whole text of a <code> element of
  its main.

Only the main of each page is read: the header and footer every page shares hold text of their own. A tree with no
reference index has none of this to check, and a part with no page is check-site.py's reference rule to name. It names
each problem it finds on stderr, one per line: the page, and each field or harness it does not name. It exits 1 when it
finds any. The Checks workflow (.github/workflows/checks.yml) runs it on the checkout, and check-schema-coverage-test.py
proves it on pages of its own that break it.

Usage: check-schema-coverage.py [--schema FILE] [ROOT]

ROOT is the folder GitHub Pages serves, site/ by default. The schema is fetched from the public app repository at the
commit the task file page's link pins, by its full SHA; --schema FILE reads FILE instead, with no network, as the tests
do. It needs only the standard library of Python 3.9 or later.
"""

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from html.parser import HTMLParser

# The reference's index, and the two parts this check reads, under ROOT.
INDEX = "docs/reference/index.html"
TASK_FILE = "docs/reference/task-file/index.html"
HARNESSES = "docs/reference/harnesses/index.html"

# A link to the task schema, pinned to a full commit SHA of the app repository; the SHA is the group.
SCHEMA_LINK = re.compile(
    r"^https://github\.com/harmflow/harmflow-app/blob/([0-9a-f]{40})/contracts/schemas/task\.schema\.json$"
)

# Any link to the task schema, pinned or not: one that pins no full SHA cannot name the schema the page describes.
ANY_SCHEMA_LINK = re.compile(
    r"^https://github\.com/harmflow/harmflow-app/blob/[^/]+/contracts/schemas/task\.schema\.json$"
)

# Where the schema is fetched from, at a commit.
SCHEMA_URL = "https://raw.githubusercontent.com/harmflow/harmflow-app/%s/contracts/schemas/task.schema.json"

# The schema's definition whose enum lists the harnesses a task may name.
PROVIDERS = "harnessProvider"

# A token of a code element or a heading: a run of letters, digits, _, and -.
TOKEN = re.compile(r"[A-Za-z0-9_-]+")

HEADINGS = ("h1", "h2", "h3", "h4", "h5", "h6")

# The keywords of a JSON Schema whose value is data, not a schema: a key there is no property name.
DATA_KEYWORDS = ("const", "default", "enum", "examples")

# The keywords whose value maps names of their own to schemas: the names are not property names, the schemas are read.
SCHEMA_MAPS = ("$defs", "definitions", "dependentSchemas", "patternProperties")


class Main(HTMLParser):
    """What a page's main holds: the text of each code element and of each heading, and its links."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.codes = []
        self.headings = []
        self.links = []
        self._main = 0
        self._open = []  # the code and heading elements open now, each (tag, its text so far)

    def handle_starttag(self, tag, attrs):
        if tag == "main":
            self._main += 1
        elif not self._main:
            return
        elif tag == "code" or tag in HEADINGS:
            self._open.append((tag, []))
        elif tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(href)

    def handle_endtag(self, tag):
        if tag == "main" and self._main:
            self._main -= 1
        elif self._main and (tag == "code" or tag in HEADINGS):
            for i in range(len(self._open) - 1, -1, -1):
                if self._open[i][0] == tag:
                    _, text = self._open.pop(i)
                    (self.codes if tag == "code" else self.headings).append("".join(text))
                    break

    def handle_data(self, data):
        for _, text in self._open:
            text.append(data)


def read_main(root, rel):
    """The main of the page ROOT/REL, or None when there is no such page."""
    path = os.path.join(root, rel)
    if not os.path.isfile(path):
        return None
    main = Main()
    with open(path, encoding="utf-8") as f:
        main.feed(f.read())
    main.close()
    return main


def tokens(main):
    """Every token of the main's code elements and headings."""
    found = set()
    for text in main.codes + main.headings:
        found.update(TOKEN.findall(text))
    return found


def property_names(schema):
    """Every property name schema defines, at every depth: the keys of every `properties` object, in $defs and
    inline, read wherever a schema can sit — under allOf, if and then, items, and the rest."""
    names = set()

    def walk(node):
        if isinstance(node, list):
            for item in node:
                walk(item)
        elif isinstance(node, dict):
            for key, value in node.items():
                if key in DATA_KEYWORDS:
                    continue
                if key == "properties" and isinstance(value, dict):
                    names.update(value)
                    walk(list(value.values()))
                elif key in SCHEMA_MAPS and isinstance(value, dict):
                    walk(list(value.values()))
                else:
                    walk(value)

    walk(schema)
    return names


def harness_providers(schema):
    """The values of the schema's harnessProvider enum, or None when it has none."""
    definition = schema.get("$defs", {}).get(PROVIDERS) if isinstance(schema, dict) else None
    values = definition.get("enum") if isinstance(definition, dict) else None
    if not isinstance(values, list) or not all(isinstance(value, str) for value in values):
        return None
    return values


def fetch_schema(sha, attempts=3):
    """The task schema at the app repository's commit sha, parsed, or raises OSError naming what failed."""
    url = SCHEMA_URL % sha
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(url, timeout=30) as answer:
                return json.loads(answer.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code < 500 or attempt == attempts - 1:
                raise OSError("%s answers %d" % (url, e.code))
        except (urllib.error.URLError, OSError) as e:
            if attempt == attempts - 1:
                raise OSError("%s cannot be fetched: %s" % (url, getattr(e, "reason", e)))
        time.sleep(2)
    raise OSError("%s cannot be fetched" % url)


def pinned_schema(rel, main):
    """The commit the main's links to the task schema pin, and the problems with those links."""
    pinned = []
    problems = []
    for href in main.links:
        match = SCHEMA_LINK.match(href)
        if match:
            if match.group(1) not in pinned:
                pinned.append(match.group(1))
        elif ANY_SCHEMA_LINK.match(href):
            problems.append("%s: its link to the task schema pins no full commit SHA: %s" % (rel, href))
    if len(pinned) > 1:
        problems.append("%s: its links to the task schema pin %d commits: %s" % (rel, len(pinned), ", ".join(pinned)))
    elif not pinned and not problems:
        problems.append("%s: its main has no link to the task schema at a pinned commit" % rel)
    return (pinned[0] if len(pinned) == 1 else None), problems


def check(root, schema=None, fetch=fetch_schema):
    """The problems of the task file and harnesses pages under root, and what was checked: the number of fields and of
    harnesses. schema, when given, is the task schema both pages are read against; otherwise the one the task file
    page pins is fetched."""
    if not os.path.isfile(os.path.join(root, INDEX)):
        return [], (0, 0)
    task_file = read_main(root, TASK_FILE)
    harnesses = read_main(root, HARNESSES)
    problems = []
    if schema is None:
        if task_file is None:  # no page to read the pin from: check-site.py names the missing part
            return [], (0, 0)
        sha, problems = pinned_schema(TASK_FILE, task_file)
        if sha is None:
            return problems, (0, 0)
        try:
            schema = fetch(sha)
        except Exception as e:  # a schema that cannot be fetched or read fails the check, not the script
            return ["%s: the task schema cannot be read: %s" % (TASK_FILE, str(e).splitlines()[0])], (0, 0)

    fields = 0
    if task_file is not None:
        names = property_names(schema)
        fields = len(names)
        if not names:
            problems.append("%s: the task schema defines no property to name" % TASK_FILE)
        for name in sorted(names - tokens(task_file)):
            problems.append("%s: its main does not name the task schema's field %s" % (TASK_FILE, name))

    providers = []
    if harnesses is not None:
        providers = harness_providers(schema) or []
        if not providers:
            problems.append("%s: the task schema has no %s enum to read the harnesses from" % (HARNESSES, PROVIDERS))
        codes = set(" ".join(text.split()) for text in harnesses.codes)
        for provider in providers:
            if provider not in codes:
                problems.append("%s: no <code> of its main reads the harness %s" % (HARNESSES, provider))
    return problems, (fields, len(providers))


def main(argv):
    args = argv[1:]
    schema_file = None
    if args[:1] == ["--schema"] and len(args) >= 2:
        schema_file = args[1]
        args = args[2:]
    if len(args) > 1 or (args and args[0].startswith("-")):
        print("usage: check-schema-coverage.py [--schema FILE] [ROOT]", file=sys.stderr)
        return 2
    root = args[0] if args else "site"
    if not os.path.isdir(root):
        print("check-schema-coverage: %s is not a directory" % root, file=sys.stderr)
        return 2
    schema = None
    if schema_file is not None:
        try:
            with open(schema_file, encoding="utf-8") as f:
                schema = json.load(f)
        except (OSError, ValueError) as e:
            print("check-schema-coverage: %s cannot be read as a schema: %s" % (schema_file, e), file=sys.stderr)
            return 2
    problems, (fields, providers) = check(root, schema)
    for problem in problems:
        print("check-schema-coverage: " + problem, file=sys.stderr)
    if problems:
        print("check-schema-coverage: %d problems" % len(problems), file=sys.stderr)
        return 1
    print(
        "check-schema-coverage: ok: the task file page names the task schema's %d fields, and the harnesses page its "
        "%d harnesses" % (fields, providers)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

#!/usr/bin/env python3
"""Checks the task file samples of the technical reference: that every sample a reference page offers as a task file
is one the app's task schema accepts. A sample is a <pre><code> block of a page under docs/reference/ whose text starts
with `apiVersion: harmflow/v1alpha1`, found by its text, so a sample added later is checked with no change here. Each
one is parsed as YAML and validated against the task schema at the commit of harmflow-app that the page's link to
contracts/schemas/task.schema.json pins, since the page describes the app at that commit. It names each problem it
finds on stderr, one per line: the page, the sample by its order on the page and the heading above it, and what is
wrong, the schema's first error with its path in the document. It exits 1 when it finds any. The Checks workflow
(.github/workflows/checks.yml) runs it on the checkout, and check-samples-test.py proves it on pages of its own that
break it.

Usage: check-samples.py [--schema FILE] [ROOT]

ROOT is the folder GitHub Pages serves, site/ by default. The schema is fetched from the public app repository at the
commit the page's link pins, by its full SHA; --schema FILE validates every sample against FILE instead, with no
network, as the tests do.

Needs PyYAML and jsonschema, which the standard library does not have: pip install PyYAML jsonschema.
"""

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from html.parser import HTMLParser

# The pages whose samples the check reads, under ROOT.
REFERENCE = "docs/reference"

# What a sample's text starts with: the task file's first key, with the only value it takes.
SAMPLE_START = "apiVersion: harmflow/v1alpha1"

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

HEADINGS = ("h1", "h2", "h3", "h4", "h5", "h6")


class Page(HTMLParser):
    """A page's code blocks inside <pre>, each with the text of the last heading above it, and its links."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks = []  # (heading, text)
        self.links = []
        self.heading = None
        self._heading_text = None
        self._pre = 0
        self._code = None

    def handle_starttag(self, tag, attrs):
        if tag in HEADINGS:
            self._heading_text = []
        elif tag == "pre":
            self._pre += 1
        elif tag == "code" and self._pre and self._code is None:
            self._code = []
        elif tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(href)

    def handle_endtag(self, tag):
        if tag in HEADINGS and self._heading_text is not None:
            self.heading = " ".join("".join(self._heading_text).split())
            self._heading_text = None
        elif tag == "pre" and self._pre:
            self._pre -= 1
        elif tag == "code" and self._code is not None:
            self.blocks.append((self.heading, "".join(self._code)))
            self._code = None

    def handle_data(self, data):
        if self._heading_text is not None:
            self._heading_text.append(data)
        if self._code is not None:
            self._code.append(data)


def reference_pages(root):
    """The HTML files under ROOT/docs/reference/, as paths from ROOT, in a stable order."""
    found = []
    for dirpath, dirnames, filenames in os.walk(os.path.join(root, REFERENCE)):
        dirnames.sort()
        for name in sorted(filenames):
            if name.endswith(".html"):
                found.append(os.path.relpath(os.path.join(dirpath, name), root).replace(os.sep, "/"))
    return found


def read_page(root, rel):
    page = Page()
    with open(os.path.join(root, rel), encoding="utf-8") as f:
        page.feed(f.read())
    page.close()
    return page


def samples(page):
    """The page's samples, each (order on the page, heading above it, text), counted from 1 among its samples."""
    found = []
    for heading, text in page.blocks:
        if text.lstrip().startswith(SAMPLE_START):
            found.append((len(found) + 1, heading, text))
    return found


def name_sample(rel, order, heading):
    under = ', under "%s"' % heading if heading else ""
    return "%s: sample %d%s" % (rel, order, under)


def yaml_loader():
    """A safe loader that reads plain scalars as YAML 1.2 does, as the daemon's parser does: only true and false are
    booleans, so `on`, `yes`, and `no` stay text, and a date or a time stays text rather than becoming a timestamp."""
    import yaml

    class Loader(yaml.SafeLoader):
        pass

    dropped = ("tag:yaml.org,2002:bool", "tag:yaml.org,2002:timestamp")
    Loader.yaml_implicit_resolvers = {
        first: [(tag, regexp) for tag, regexp in resolvers if tag not in dropped]
        for first, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
    }
    boolean = re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$")
    Loader.add_implicit_resolver("tag:yaml.org,2002:bool", boolean, list("tTfF"))
    return Loader


def place(path):
    """A path in the document as the reader writes it: spec.harness.fallback.candidates[0].provider."""
    written = ""
    for part in path:
        if isinstance(part, int):
            written += "[%d]" % part
        else:
            written += ("." if written else "") + str(part)
    return written or "the document's root"


def first_error(validator, document):
    """The schema's first error on document, the one jsonschema ranks as most relevant, or None."""
    from jsonschema.exceptions import best_match

    error = best_match(validator.iter_errors(document))
    if error is None:
        return None
    return "%s: %s" % (place(error.absolute_path), error.message)


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


def pinned_schema(rel, page):
    """The commit the page's links to the task schema pin, and the problems with those links."""
    pinned = []
    problems = []
    for href in page.links:
        match = SCHEMA_LINK.match(href)
        if match:
            if match.group(1) not in pinned:
                pinned.append(match.group(1))
        elif ANY_SCHEMA_LINK.match(href):
            problems.append("%s: its link to the task schema pins no full commit SHA: %s" % (rel, href))
    if len(pinned) > 1:
        problems.append("%s: its links to the task schema pin %d commits: %s" % (rel, len(pinned), ", ".join(pinned)))
    elif not pinned and not problems:
        problems.append("%s: it holds task file samples but no link to the task schema at a pinned commit" % rel)
    return (pinned[0] if len(pinned) == 1 else None), problems


def validator_of(schema):
    """A draft 2020-12 validator of schema, or raises an error naming what makes it no valid schema."""
    from jsonschema import Draft202012Validator

    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def check(root, schema=None, fetch=fetch_schema):
    """The problems of the reference's samples under root, and the number of samples read. schema, when given, is the
    task schema every sample is validated against; otherwise each page's pinned schema is fetched, once a commit."""
    import yaml

    loader = yaml_loader()
    validators = {}  # by pinned commit, None for the schema given; each a validator or the problem reading it
    problems = []
    count = 0
    for rel in reference_pages(root):
        page = read_page(root, rel)
        found = samples(page)
        if not found:
            continue
        count += len(found)
        sha = None
        if schema is None:
            sha, link_problems = pinned_schema(rel, page)
            problems += link_problems
            if sha is None:
                continue
        if sha not in validators:
            try:
                validators[sha] = validator_of(schema if sha is None else fetch(sha))
            except Exception as e:  # a schema that cannot be fetched or read fails the check, not the script
                validators[sha] = "the task schema cannot be read: %s" % str(e).splitlines()[0]
        validator = validators[sha]
        if isinstance(validator, str):
            problems.append("%s: %s" % (rel, validator))
            continue
        for order, heading, text in found:
            name = name_sample(rel, order, heading)
            try:
                document = yaml.load(text, Loader=loader)
            except yaml.YAMLError as e:
                mark = getattr(e, "problem_mark", None)
                where = " at line %d" % (mark.line + 1) if mark is not None else ""
                problem = getattr(e, "problem", None) or str(e).splitlines()[0]
                problems.append("%s: is not YAML%s: %s" % (name, where, problem))
                continue
            error = first_error(validator, document)
            if error:
                problems.append("%s: the task schema rejects it at %s" % (name, error))
    return problems, count


def main(argv):
    args = argv[1:]
    schema_file = None
    if args[:1] == ["--schema"] and len(args) >= 2:
        schema_file = args[1]
        args = args[2:]
    if len(args) > 1 or (args and args[0].startswith("-")):
        print("usage: check-samples.py [--schema FILE] [ROOT]", file=sys.stderr)
        return 2
    root = args[0] if args else "site"
    if not os.path.isdir(root):
        print("check-samples: %s is not a directory" % root, file=sys.stderr)
        return 2
    try:
        import jsonschema  # noqa: F401
        import yaml  # noqa: F401
    except ImportError:
        print("check-samples: needs PyYAML and jsonschema: pip install PyYAML jsonschema", file=sys.stderr)
        return 2
    schema = None
    if schema_file is not None:
        try:
            with open(schema_file, encoding="utf-8") as f:
                schema = json.load(f)
        except (OSError, ValueError) as e:
            print("check-samples: %s cannot be read as a schema: %s" % (schema_file, e), file=sys.stderr)
            return 2
    problems, count = check(root, schema)
    for problem in problems:
        print("check-samples: " + problem, file=sys.stderr)
    if problems:
        print("check-samples: %d problems" % len(problems), file=sys.stderr)
        return 1
    print("check-samples: ok: %d task file samples, each valid against the task schema" % count)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

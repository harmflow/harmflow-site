#!/usr/bin/env python3
"""Checks that the technical reference names every operation of the local API: each path of the OpenAPI description
with each of its methods, read from contracts/api/openapi.yaml at the commit of harmflow-app that the local API page's
link to it pins, since the page describes the app at that commit. An operation counts as named when the main of the
local API page or of the harnesses page names it in one of these forms, the forms the pages use:

- a <code> element that reads the method and the path as the description writes it: `<code>GET /tasks</code>`;
- the same, with a path parameter given one of the values its enum allows:
  `<code>POST /harnesses/claude-code/sign-in</code>` names `POST /harnesses/{harnessId}/sign-in`;
- methods in <code> elements of their own, before such an element in the same list item or paragraph:
  `<code>GET</code>, <code>PUT</code>, and <code>DELETE /tasks/{taskId}</code>` names those three operations;
- a <code> element holding a single path segment, after such an element in the same list item or paragraph, standing
  for that element's path with its last segment replaced, and the same method:
  `<code>POST /tasks/{taskId}/run</code> ... <code>/enable</code>` names `POST /tasks/{taskId}/enable`.

Only the main of each page is read: the header and footer every page shares hold text of their own. A tree with no
reference index has none of this to check, and a part with no page is check-site.py's reference rule to name. It names
each operation no form names on stderr, one per line, by its method and path, and exits 1 when it finds any. The Checks
workflow (.github/workflows/checks.yml) runs it on the checkout, and check-api-coverage-test.py proves it on pages of
its own that break it.

Usage: check-api-coverage.py [--description FILE] [ROOT]

ROOT is the folder GitHub Pages serves, site/ by default. The description is fetched from the public app repository at
the commit the local API page's link pins, by its full SHA; --description FILE reads FILE instead, with no network, as
the tests do.

Needs PyYAML, which the standard library does not have: pip install PyYAML.
"""

import os
import re
import sys
import time
import urllib.error
import urllib.request
from html.parser import HTMLParser

# The reference's index, and the two parts that name the API's operations, under ROOT.
INDEX = "docs/reference/index.html"
LOCAL_API = "docs/reference/local-api/index.html"
HARNESSES = "docs/reference/harnesses/index.html"

# A link to the API description, pinned to a full commit SHA of the app repository; the SHA is the group.
DESCRIPTION_LINK = re.compile(
    r"^https://github\.com/harmflow/harmflow-app/blob/([0-9a-f]{40})/contracts/api/openapi\.yaml$"
)

# Any link to the API description, pinned or not: one that pins no full SHA cannot name the description the page
# describes.
ANY_DESCRIPTION_LINK = re.compile(r"^https://github\.com/harmflow/harmflow-app/blob/[^/]+/contracts/api/openapi\.yaml$")

# Where the description is fetched from, at a commit.
DESCRIPTION_URL = "https://raw.githubusercontent.com/harmflow/harmflow-app/%s/contracts/api/openapi.yaml"

# The methods of an OpenAPI path item, in the order a failure lists them.
METHODS = ("get", "put", "post", "delete", "options", "head", "patch", "trace")
METHOD = "(%s)" % "|".join(method.upper() for method in METHODS)

# The forms a <code> element's text takes, its whitespace collapsed: a method and a path, a method alone, and a single
# path segment.
OPERATION = re.compile(r"^%s (/\S*)$" % METHOD)
BARE_METHOD = re.compile(r"^%s$" % METHOD)
SEGMENT = re.compile(r"^/[^/\s]+$")

# The elements whose <code> elements make one list item or paragraph, for the forms that read more than one.
BLOCKS = ("li", "p")

# A path parameter in a path template.
PARAMETER = re.compile(r"^\{([^{}/]+)\}$")


class Main(HTMLParser):
    """What a page's main holds: its links, and the text of each <code> element with the list item or paragraph it is
    in, the innermost one, or None outside any."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.codes = []  # (block, text), in the page's order; block is a number per list item or paragraph
        self.links = []
        self._main = 0
        self._blocks = []  # the list items and paragraphs open now, each (tag, its number)
        self._count = 0
        self._code = None
        self._depth = 0

    def handle_starttag(self, tag, attrs):
        if tag == "main":
            self._main += 1
        elif not self._main:
            return
        elif tag in BLOCKS:
            self._count += 1
            self._blocks.append((tag, self._count))
        elif tag == "code":
            if self._code is None:
                self._code = []
                self._depth = 0
            self._depth += 1
        elif tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(href)

    def handle_endtag(self, tag):
        if tag == "main" and self._main:
            self._main -= 1
        elif not self._main:
            return
        elif tag in BLOCKS:
            for i in range(len(self._blocks) - 1, -1, -1):
                if self._blocks[i][0] == tag:
                    del self._blocks[i:]
                    break
        elif tag == "code" and self._code is not None:
            self._depth -= 1
            if not self._depth:
                block = self._blocks[-1][1] if self._blocks else None
                self.codes.append((block, " ".join("".join(self._code).split())))
                self._code = None

    def handle_data(self, data):
        if self._code is not None:
            self._code.append(data)


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


def written_operations(main):
    """Each (METHOD, path) the main writes, in any of the forms."""
    found = []
    block = object()
    methods = []  # the methods of their own since the last method and path, in this block
    last = None  # the last method and path of this block
    for where, text in main.codes:
        if where != block or where is None:
            block, methods, last = where, [], None
        match = OPERATION.match(text)
        if match:
            method, path = match.groups()
            found.append((method, path))
            found.extend((other, path) for other in methods)
            methods, last = [], (method, path)
        elif BARE_METHOD.match(text):
            methods.append(text)
        elif SEGMENT.match(text) and last is not None:
            method, path = last
            found.append((method, path.rsplit("/", 1)[0] + text))
    return found


def resolve(document, node):
    """node, or what its $ref points to in document when it is a reference to one of document's own parts."""
    seen = 0
    while isinstance(node, dict) and isinstance(node.get("$ref"), str) and node["$ref"].startswith("#/"):
        target = document
        for part in node["$ref"][2:].split("/"):
            part = part.replace("~1", "/").replace("~0", "~")
            target = target.get(part) if isinstance(target, dict) else None
        node = target
        seen += 1
        if seen > 20:
            return None
    return node


def path_values(document, item, operation):
    """Each path parameter of the operation, by name, with the values its enum allows, empty when it has none. An
    operation's parameter overrides the path item's of the same name."""
    values = {}
    for parameter in list(item.get("parameters") or []) + list(operation.get("parameters") or []):
        parameter = resolve(document, parameter)
        if not isinstance(parameter, dict) or parameter.get("in") != "path":
            continue
        schema = resolve(document, parameter.get("schema")) or {}
        enum = schema.get("enum") if isinstance(schema, dict) else None
        values[parameter.get("name")] = [str(value) for value in enum] if isinstance(enum, list) else []
    return values


def operations(document):
    """Each operation of the description, (METHOD, path, a pattern its written forms match), in the description's
    order. A segment that is a path parameter matches the parameter as written or one of its enum's values."""
    found = []
    paths = document.get("paths") if isinstance(document, dict) else None
    for path, item in (paths or {}).items():
        item = resolve(document, item)
        if not isinstance(item, dict):
            continue
        for method in METHODS:
            operation = item.get(method)
            if not isinstance(operation, dict):
                continue
            values = path_values(document, item, operation)
            segments = []
            for segment in path.split("/"):
                parameter = PARAMETER.match(segment)
                choices = [segment] + (values.get(parameter.group(1), []) if parameter else [])
                segments.append("(?:%s)" % "|".join(re.escape(choice) for choice in choices))
            found.append((method.upper(), path, re.compile("^%s$" % "/".join(segments))))
    return found


def fetch_description(sha, attempts=3):
    """The API description at the app repository's commit sha, as text, or raises OSError naming what failed."""
    url = DESCRIPTION_URL % sha
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(url, timeout=30) as answer:
                return answer.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            if e.code < 500 or attempt == attempts - 1:
                raise OSError("%s answers %d" % (url, e.code))
        except (urllib.error.URLError, OSError) as e:
            if attempt == attempts - 1:
                raise OSError("%s cannot be fetched: %s" % (url, getattr(e, "reason", e)))
        time.sleep(2)
    raise OSError("%s cannot be fetched" % url)


def pinned_description(rel, main):
    """The commit the main's links to the API description pin, and the problems with those links."""
    pinned = []
    problems = []
    for href in main.links:
        match = DESCRIPTION_LINK.match(href)
        if match:
            if match.group(1) not in pinned:
                pinned.append(match.group(1))
        elif ANY_DESCRIPTION_LINK.match(href):
            problems.append("%s: its link to the API description pins no full commit SHA: %s" % (rel, href))
    if len(pinned) > 1:
        problems.append(
            "%s: its links to the API description pin %d commits: %s" % (rel, len(pinned), ", ".join(pinned))
        )
    elif not pinned and not problems:
        problems.append("%s: its main has no link to the API description at a pinned commit" % rel)
    return (pinned[0] if len(pinned) == 1 else None), problems


def parse(text):
    """The description's text, parsed, or raises ValueError naming what is wrong."""
    import yaml

    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise ValueError("it is not YAML: %s" % (getattr(e, "problem", None) or str(e).splitlines()[0]))
    if not isinstance(document, dict) or not isinstance(document.get("paths"), dict):
        raise ValueError("it has no paths")
    return document


def check(root, description=None, fetch=fetch_description):
    """The problems of the reference under root, and the number of operations read. description, when given, is the
    API description's text the pages are read against; otherwise the one the local API page pins is fetched."""
    if not os.path.isfile(os.path.join(root, INDEX)):
        return [], 0
    pages = [(rel, read_main(root, rel)) for rel in (LOCAL_API, HARNESSES)]
    local_api = pages[0][1]
    if description is None:
        if local_api is None:  # no page to read the pin from: check-site.py names the missing part
            return [], 0
        sha, problems = pinned_description(LOCAL_API, local_api)
        if sha is None:
            return problems, 0
        try:
            description = fetch(sha)
        except Exception as e:  # a description that cannot be fetched fails the check, not the script
            return ["%s: the API description cannot be read: %s" % (LOCAL_API, str(e).splitlines()[0])], 0
    try:
        document = parse(description)
    except ValueError as e:
        return ["%s: the API description cannot be read: %s" % (LOCAL_API, e)], 0

    written = []
    for _, main in pages:
        if main is not None:
            written += written_operations(main)
    problems = []
    found = operations(document)
    for method, path, pattern in found:
        if not any(method == other and pattern.match(where) for other, where in written):
            problems.append(
                "%s %s: named nowhere in the main of %s or %s" % (method, path, LOCAL_API, HARNESSES)
            )
    return problems, len(found)


def main(argv):
    args = argv[1:]
    description_file = None
    if args[:1] == ["--description"] and len(args) >= 2:
        description_file = args[1]
        args = args[2:]
    if len(args) > 1 or (args and args[0].startswith("-")):
        print("usage: check-api-coverage.py [--description FILE] [ROOT]", file=sys.stderr)
        return 2
    root = args[0] if args else "site"
    if not os.path.isdir(root):
        print("check-api-coverage: %s is not a directory" % root, file=sys.stderr)
        return 2
    try:
        import yaml  # noqa: F401
    except ImportError:
        print("check-api-coverage: needs PyYAML: pip install PyYAML", file=sys.stderr)
        return 2
    description = None
    if description_file is not None:
        try:
            with open(description_file, encoding="utf-8") as f:
                description = f.read()
        except OSError as e:
            print("check-api-coverage: %s cannot be read: %s" % (description_file, e), file=sys.stderr)
            return 2
    problems, count = check(root, description)
    for problem in problems:
        print("check-api-coverage: " + problem, file=sys.stderr)
    if problems:
        print("check-api-coverage: %d problems" % len(problems), file=sys.stderr)
        return 1
    print("check-api-coverage: ok: the reference names each of the local API's %d operations" % count)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

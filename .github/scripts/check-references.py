#!/usr/bin/env python3
"""Checks that nothing this public repository publishes references a private record, names a repository of the
organization that is not public, or carries a personal identifier. It reads every tracked text file of ROOT (a binary
file is skipped), and, on a pull request, every commit message from its base to its head and the pull request's title
and body. It names each finding on stderr, one per line, with its place and its rule's label, and never the text it
matched or a pattern: the log of a public repository's run is public. It exits 1 when it finds any.

The rules come in two tiers.

- The public rules, committed here, name only public things:
  - repository: a repository of the harmflow organization other than the public ones PUBLIC_REPOSITORIES holds,
    written as a GitHub address of the organization, as the organization and a repository's name joined by a slash,
    or as a bare name with the organization's prefix and a hyphen. The organization names every repository so, but
    .github; the organization and a slash before any other word, as a task file's apiVersion writes it, is no
    repository.
  - e-mail: an e-mail address outside harmflow.com and GitHub's own domains, which Dependabot's and GitHub's commit
    trailers use. A name with a scale before an image's extension, as a high-density image is named, is no address.
  - account identifier: an identifier of the forms Google's tags and ads use, other than the site's measurement ID,
    which ALLOWED_IDENTIFIERS holds: a tag ID (G-, GT-, AW-, or DC- and its letters and digits), a Universal Analytics
    property (UA-, digits, a hyphen, and digits), a Tag Manager container (GTM- and its letters and digits), or an
    AdSense publisher ID (ca-pub- and digits). The site's analytics property is a HarmFlow account's, and its
    measurement ID, which every page carries, is the one account-linked identifier the repository holds. A word that
    only resembles a prefix, as a hyphenated word in prose, is no identifier.
- The private rules, one regular expression per line, describe the private documentation's record identifiers and the
  owner's own identifiers. Committed, they would publish what they keep private, so they are read at run time and never
  committed: from --patterns FILE, a file outside the clone, or from the PRIVATE_REFERENCE_PATTERNS environment
  variable, which CI fills from the repository's secret of that name. A pattern's label is "private pattern <n>", n
  being its line in the list. Each pattern is matched against each line.

PRIVATE_RULES says what a run does without the patterns. "required", which CI sets on a push to main and on a pull
request from a branch of this repository not opened by Dependabot, fails the run, so a deleted secret cannot turn the
private rules off in silence. "optional", which CI sets on a pull request from a fork or one Dependabot opens, which
cannot read the secret by design, skips them, says so in the job's summary ($GITHUB_STEP_SUMMARY), and passes on the
public rules alone. Unset, as locally, it skips them and says so on stderr.

On a pull request, --base and --head name its base and head commits, whose messages it reads, and PR_TITLE and
PR_BODY, set through the workflow's env:, hold its title and body. The References workflow
(.github/workflows/references.yml) runs it, and check-references-test.py proves each rule on a repository of its own
that breaks it.

Usage: check-references.py [--patterns FILE] [--base SHA --head SHA] [ROOT]

ROOT is the clone to read, the current directory by default.

The standard library only, and Python 3.9, so it runs on a Mac's own python3 as it does in CI.
"""

import argparse
import os
import re
import subprocess
import sys

ORGANIZATION = "harmflow"

# The organization's public repositories. The rule holds this list, never another repository's name.
PUBLIC_REPOSITORIES = ("harmflow-app", "harmflow-site", ".github")

# The characters of a repository's name on GitHub.
NAME = r"[A-Za-z0-9_.-]+"

# Where a name may start: not inside a longer name or path segment.
START = r"(?<![A-Za-z0-9_.-])"

# The three ways to write a repository of the organization. The address is read in any case, as GitHub reads it; the
# other two in lower case, as the organization writes its names, so prose that hyphenates the product's name is no
# repository. The organization and a slash count only before a name with the prefix, or .github's leading dot.
REPOSITORY_FORMS = (
    re.compile(r"github\.com/" + ORGANIZATION + "/(" + NAME + ")", re.IGNORECASE),
    re.compile(START + ORGANIZATION + "/(" + ORGANIZATION + "-" + NAME + r"|\." + NAME + ")"),
    re.compile(START + "(" + ORGANIZATION + "-" + NAME + ")"),
)

# An e-mail address: a local part, the at sign, and a domain whose last label is letters.
EMAIL = re.compile(r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]+" + "@" + r"([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,})")

# The domains an address may have, with their subdomains: the project's own, and GitHub's, whose no-reply addresses
# Dependabot's and GitHub's commit trailers use.
ALLOWED_DOMAINS = ("harmflow.com", "github.com")

# File extensions that are no top-level domain: a file named with an at sign before one of them, as a high-density
# image's name holds its scale, is a file, not an address.
FILE_EXTENSIONS = ("avif", "css", "gif", "html", "ico", "jpeg", "jpg", "js", "mp4", "pdf", "png", "svg", "webm", "webp")

# An identifier of Google's tags and ads: a tag ID, a Tag Manager container, a Universal Analytics property, or an
# AdSense publisher ID. Their letters are upper case and they run to six characters or more, so a hyphenated word in
# prose ("G-rated", "a DC-3") is none; a letter, digit, or hyphen before one, or a letter or digit after it, makes it
# part of a longer word.
GOOGLE_IDENTIFIER = re.compile(
    START + r"((?:GTM|GT|G|AW|DC)-[A-Z0-9]{6,}|UA-[0-9]{4,}-[0-9]+|ca-pub-[0-9]{6,})(?![A-Za-z0-9_])"
)

# The identifiers the repository may hold: the site's measurement ID, which site/scripts/consent.js carries, and every
# page with it.
ALLOWED_IDENTIFIERS = ("G-X0TY5Z9VFR",)

REPOSITORY = "repository"
E_MAIL = "e-mail"
ACCOUNT_IDENTIFIER = "account identifier"

DESCRIPTIONS = {
    REPOSITORY: "names a repository of the organization that is not public",
    E_MAIL: "holds an e-mail address outside harmflow.com and GitHub's domains",
    ACCOUNT_IDENTIFIER: "holds an identifier of Google's tags or ads other than the site's measurement ID",
}

# How many bytes a file's start is read for a NUL byte, which marks it binary, as git decides it.
BINARY_PROBE = 8000


class Usage(Exception):
    """A problem with how the check was run, not a finding: it exits 2."""


def git(root, *args):
    result = subprocess.run(
        ["git", "-C", root] + list(args), stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False
    )
    if result.returncode != 0:
        raise Usage("git %s failed: %s" % (args[0], result.stderr.decode("utf-8", "replace").strip()))
    return result.stdout


def tracked_texts(root):
    """Each tracked text file of ROOT as (path, text), in git's order. A binary file, a submodule, and a file missing
    from the worktree are skipped; a symbolic link is read as the path it holds."""
    for raw in git(root, "ls-files", "-z").split(b"\0"):
        if not raw:
            continue
        rel = raw.decode("utf-8", "surrogateescape")
        path = os.path.join(root, rel)
        if os.path.islink(path):
            yield rel, os.readlink(path)
            continue
        if not os.path.isfile(path):
            continue
        with open(path, "rb") as f:
            data = f.read()
        if b"\0" in data[:BINARY_PROBE]:
            continue
        yield rel, data.decode("utf-8", "replace")


def commit_messages(root, base, head):
    """The message of each commit from BASE to HEAD as (sha, message), newest first."""
    out = git(root, "log", "-z", "--format=%H%n%B", "%s..%s" % (base, head)).decode("utf-8", "replace")
    for record in out.split("\0"):
        if not record.strip():
            continue
        sha, _, message = record.lstrip("\n").partition("\n")
        yield sha, message


def read_patterns(text):
    """The private patterns of TEXT, one per line, as (line, compiled pattern). A blank line holds none but counts."""
    patterns = []
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            patterns.append((number, re.compile(line)))
        except re.error as error:
            # The error's position only: its message may quote the pattern.
            raise Usage("private pattern %d is not a valid regular expression (at position %s)" % (number, error.pos))
    return patterns


def repository_names(line):
    for form in REPOSITORY_FORMS:
        for match in form.finditer(line):
            name = match.group(1).rstrip(".").lower()
            if name.endswith(".git"):
                name = name[: -len(".git")]
            yield name


def e_mail_domains(line):
    for match in EMAIL.finditer(line):
        domain = match.group(1).lower()
        if domain.rsplit(".", 1)[-1] in FILE_EXTENSIONS:
            continue
        yield domain


def allowed(domain):
    return any(domain == d or domain.endswith("." + d) for d in ALLOWED_DOMAINS)


def labels(line, patterns):
    """The labels of the rules LINE breaks, in the rules' order."""
    found = []
    if any(name not in PUBLIC_REPOSITORIES for name in repository_names(line)):
        found.append(REPOSITORY)
    if any(not allowed(domain) for domain in e_mail_domains(line)):
        found.append(E_MAIL)
    if any(match.group(1) not in ALLOWED_IDENTIFIERS for match in GOOGLE_IDENTIFIER.finditer(line)):
        found.append(ACCOUNT_IDENTIFIER)
    for number, pattern in patterns:
        if pattern.search(line):
            found.append("private pattern %d" % number)
    return found


def check_text(text, place, patterns):
    """The findings of TEXT, each as (place, label). PLACE gives the place of a line from its number."""
    findings = []
    for number, line in enumerate(text.splitlines(), 1):
        for label in labels(line, patterns):
            findings.append((place(number), label))
    return findings


def describe(label):
    return DESCRIPTIONS.get(label, "matches a private rule")


def plural(count, noun):
    return "%d %s%s" % (count, noun, "" if count == 1 else "s")


def summary(text):
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(text + "\n")


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--patterns", metavar="FILE", help="the private patterns, one regular expression per line")
    parser.add_argument("--base", metavar="SHA", help="a pull request's base commit")
    parser.add_argument("--head", metavar="SHA", help="a pull request's head commit")
    parser.add_argument("root", nargs="?", default=".", metavar="ROOT")
    args = parser.parse_args(argv)
    if bool(args.base) != bool(args.head):
        parser.error("--base and --head go together")

    try:
        if args.patterns:
            with open(args.patterns, encoding="utf-8") as f:
                source = f.read()
        else:
            source = os.environ.get("PRIVATE_REFERENCE_PATTERNS", "")
        patterns = read_patterns(source)
        mode = os.environ.get("PRIVATE_RULES", "")
        if mode not in ("", "required", "optional"):
            raise Usage('PRIVATE_RULES is "required", "optional", or unset')

        findings = []
        files = 0
        for rel, text in tracked_texts(args.root):
            files += 1
            findings += check_text(text, lambda n, rel=rel: "%s:%d" % (rel, n), patterns)
        commits = 0
        if args.base:
            for sha, message in commit_messages(args.root, args.base, args.head):
                commits += 1
                findings += check_text(message, lambda n, sha=sha: "commit %s, line %d" % (sha[:12], n), patterns)
        title = os.environ.get("PR_TITLE")
        if title is not None:
            findings += [("pull request title", label) for label in labels(" ".join(title.splitlines()), patterns)]
        body = os.environ.get("PR_BODY")
        if body is not None:
            findings += check_text(body, lambda n: "pull request body, line %d" % n, patterns)
    except (Usage, OSError) as error:
        print("check-references: %s" % error, file=sys.stderr)
        return 2

    missing = not patterns
    if missing and mode == "required":
        print(
            "private rules: no patterns to read; this run must have the PRIVATE_REFERENCE_PATTERNS secret, so a "
            "missing or empty secret fails it",
            file=sys.stderr,
        )
    elif missing and mode == "optional":
        note = (
            "The private rules were skipped: a pull request from a fork, or one Dependabot opens, cannot read the "
            "PRIVATE_REFERENCE_PATTERNS secret. The public rules ran."
        )
        print(note, file=sys.stderr)
        summary(note)
    elif missing:
        print("Skipped the private rules: no pattern given (--patterns FILE). The public rules ran.", file=sys.stderr)

    for place, label in findings:
        print("%s: %s: %s" % (place, label, describe(label)), file=sys.stderr)

    read = plural(files, "file")
    if args.base:
        read += ", " + plural(commits, "commit message")
    if title is not None or body is not None:
        read += ", the pull request's title and body"
    if findings:
        print("%d findings in %s; the matched text is never shown." % (len(findings), read), file=sys.stderr)
        return 1
    if missing and mode == "required":
        print("No finding in %s by the public rules; the private rules could not run." % read, file=sys.stderr)
        return 1
    print("No finding in %s." % read)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

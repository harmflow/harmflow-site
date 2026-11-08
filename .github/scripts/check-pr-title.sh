#!/usr/bin/env bash
# Checks that a pull request's title is a valid subject under the organization's commit convention
# (COMMIT_CONVENTION.md in harmflow/.github): pull requests merge with Rebase and merge, and the title is what the
# convention reads. A valid title is
#
#   <type>[(<scope>)][!]: <subject>
#
# with <type> one of feat, fix, docs, refactor, test, perf, ci, chore; an optional scope in lower-case kebab-case; an
# optional ! for a breaking change; then ": " and a subject that does not start with a space; at most 72 characters in
# all, and no trailing period. A pull request Dependabot opens is checked for the format but not the length: its
# grouped updates' titles run past 72 characters, and no setting shortens them.
#
# Usage: check-pr-title.sh TITLE [AUTHOR]
#
# AUTHOR is the login of the pull request's author; dependabot[bot] lifts the length limit. The Pull request title
# workflow (.github/workflows/pr-title.yml) passes both through env:, never inside the script, and
# check-pr-title-test.sh lists titles that pass and titles that fail. It names every rule a title breaks on stderr, and
# exits 1 when it breaks any.
set -euo pipefail

if [ $# -lt 1 ] || [ $# -gt 2 ]; then
  echo "usage: check-pr-title.sh TITLE [AUTHOR]" >&2
  exit 2
fi
title=$1
author=${2:-}

types="feat|fix|docs|refactor|test|perf|ci|chore"
format="^($types)(\([a-z0-9]+(-[a-z0-9]+)*\))?!?: [^ ]"
limit=72
rule="<type>[(<scope>)][!]: <subject>, with <type> one of ${types//|/, }, an optional scope in lower-case"
rule="$rule kebab-case, at most $limit characters, and no trailing period (COMMIT_CONVENTION.md in harmflow/.github)"

problems=()
if ! [[ $title =~ $format ]]; then
  problems+=("its format is not <type>[(<scope>)][!]: <subject>")
fi
if [ "$author" != "dependabot[bot]" ] && [ "${#title}" -gt "$limit" ]; then
  problems+=("it is ${#title} characters long, over $limit")
fi
if [[ $title == *. ]]; then
  problems+=("it ends with a period")
fi

if [ ${#problems[@]} -gt 0 ]; then
  for problem in "${problems[@]}"; do
    echo "check-pr-title: $problem" >&2
  done
  echo "check-pr-title: the rule: $rule" >&2
  exit 1
fi
echo "check-pr-title: ok"

#!/usr/bin/env bash
# Tests of check-pr-title.sh: titles that pass and titles that fail, each failing one with the rule it breaks named.
# The Pull request title workflow (.github/workflows/pr-title.yml) runs it before it checks the title.
#
# Usage: check-pr-title-test.sh
set -euo pipefail

script="$(cd "$(dirname "$0")" && pwd)/check-pr-title.sh"
failures=0
count=0

# A title of N characters: "feat: " and N-6 x's.
title_of() {
  printf 'feat: %s' "$(printf '%*s' "$(($1 - 6))" '' | tr ' ' x)"
}

# passes TITLE [AUTHOR]: the check exits 0.
passes() {
  count=$((count + 1))
  if ! out=$("$script" "$@" 2>&1); then
    echo "FAIL: '$1' should pass: $out" >&2
    failures=$((failures + 1))
  fi
}

# fails TEXT TITLE [AUTHOR]: the check exits 1, names TEXT, and states the rule.
fails() {
  local text=$1
  shift
  count=$((count + 1))
  local rc=0
  out=$("$script" "$@" 2>&1) || rc=$?
  if [ "$rc" -ne 1 ] || [[ $out != *"$text"* ]] || [[ $out != *"the rule: <type>[(<scope>)][!]: <subject>"* ]]; then
    echo "FAIL: '$1' should fail with exit 1, naming '$text' and the rule; it exited $rc: $out" >&2
    failures=$((failures + 1))
  fi
}

# Titles that pass: every type, a scope, a breaking change, and exactly 72 characters.
for type in feat fix docs refactor test perf ci chore; do
  passes "$type: add the guide section on the queue panel"
done
passes "ci(checks): run zizmor over the workflows"
passes "feat(guide-install)!: move the install guide"
passes "fix!: drop the old header"
passes "docs: say what v1.2.3 changes, and why it is safe"
passes "$(title_of 72)"
passes "chore(deps): bump the github-actions group across 1 directory with 2 updates" "dependabot[bot]"

# Titles that fail, each naming what broke.
fails "its format" "Add the guide section"
fails "its format" "feature: add the guide section"
fails "its format" "Feat: add the guide section"
fails "its format" "build: bump the toolchain"
fails "its format" "feat(Guide): add the guide section"
fails "its format" "feat(guide_install): add the guide section"
fails "its format" "feat(): add the guide section"
fails "its format" "feat:add the guide section"
fails "its format" "feat:  add the guide section"
fails "its format" "feat: "
fails "its format" "feat !: add the guide section"
fails "its format" " feat: add the guide section"
fails "73 characters long, over 72" "$(title_of 73)"
fails "73 characters long, over 72" "$(title_of 73)" "a-person"
fails "ends with a period" "feat: add the guide section."
fails "ends with a period" "chore(deps): bump actions/checkout." "dependabot[bot]"
fails "its format" "Bump actions/checkout from 6 to 7" "dependabot[bot]"

# Both rules at once are both named.
fails "its format" "Add the guide section."
fails "ends with a period" "Add the guide section."

# Usage errors exit 2.
count=$((count + 1))
rc=0
"$script" >/dev/null 2>&1 || rc=$?
if [ "$rc" -ne 2 ]; then
  echo "FAIL: no title should exit 2, exited $rc" >&2
  failures=$((failures + 1))
fi

if [ "$failures" -gt 0 ]; then
  echo "check-pr-title-test: $failures of $count cases failed" >&2
  exit 1
fi
echo "check-pr-title-test: ok: $count cases"

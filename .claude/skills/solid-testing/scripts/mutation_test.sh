#!/usr/bin/env bash
# Scoped mutation testing: mutate ONLY the Python files changed since a base
# ref, so the run finishes in minutes and actually gets used. Surviving
# mutants = assertions too permissive (smells #7/#8 in checklist.md).
#
# Usage (from the repo root):
#   .claude/skills/solid-testing/scripts/mutation_test.sh              # since @{push}/origin
#   .claude/skills/solid-testing/scripts/mutation_test.sh v0.10.0      # since a ref
#
# JS note: for the frontend the equivalent is Stryker (npx stryker run) with
# `mutate` scoped the same way in stryker.config.json — heavier to set up, so
# start with the backend; the cheap manual variant for BOTH stacks is:
# re-introduce the bug / flip the condition and watch the test fail.
set -euo pipefail

BASE="${1:-}"
if [ -z "$BASE" ]; then
  BASE=$(git rev-parse --abbrev-ref --symbolic-full-name '@{push}' 2>/dev/null) \
    || BASE="origin/$(git rev-parse --abbrev-ref HEAD)"
fi

if ! command -v mutmut >/dev/null 2>&1; then
  echo "mutmut is not installed. It is a dev-only tool — install it ad hoc:"
  echo "    pip install mutmut"
  exit 1
fi

CHANGED=$(git diff --name-only "$BASE"...HEAD -- 'core/*.py' \
  | grep -v -e '/tests/' -e '/migrations/' || true)

# Deleted files are still named by `git diff`, and mutmut cannot mutate a path
# that is not there — filter to what actually exists in the working tree.
CHANGED=$(echo "$CHANGED" | while read -r f; do [ -f "$f" ] && echo "$f"; done)

if [ -z "$CHANGED" ]; then
  echo "No changed backend source files since $BASE — nothing to mutate."
  exit 0
fi

echo "Mutating files changed since $BASE:"
echo "$CHANGED" | sed 's/^/  - /'
echo

# mutmut 2 took the scope on the command line; mutmut 3 dropped
# --paths-to-mutate / --tests-dir / --runner and reads `[tool.mutmut]` in
# pyproject.toml instead. Both are supported below, because the failure this
# script had was worse than either: on 3.x the 2.x invocation errored, a `|| true`
# swallowed it, `mutmut results` printed an empty list, and the script announced
# "no surviving mutants" having mutated **nothing**, exit code 0. A tool that
# certifies a clean run it never performed is smell #7 one layer up.
run_mutmut() {
  if mutmut run --help 2>/dev/null | grep -q -- '--paths-to-mutate'; then
    rm -rf .mutmut-cache
    mutmut run --paths-to-mutate "$(echo "$CHANGED" | paste -sd, -)" \
      --tests-dir core/tests --runner "python -m pytest -x -q core/tests"
  else
    run_mutmut_3
  fi
}

# On 3.x the scope dial is `only_mutate` in pyproject.toml, so a scoped run means
# editing that file. It is restored by a trap on every exit path — including
# Ctrl-C — because leaving somebody's pyproject rewritten by a test tool would be
# a far worse bug than anything this script is looking for.
run_mutmut_3() {
  local pyproject="pyproject.toml"
  if ! grep -q '^\[tool\.mutmut\]' "$pyproject" 2>/dev/null; then
    echo "mutmut 3.x needs a [tool.mutmut] section in $pyproject (source_paths," >&2
    echo "pytest_add_cli_args_test_selection, also_copy). See the repo's own." >&2
    return 1
  fi

  cp "$pyproject" "$pyproject.mutation-bak"
  # shellcheck disable=SC2064 — $pyproject is expanded now, deliberately.
  trap "mv -f '$pyproject.mutation-bak' '$pyproject'" EXIT INT TERM

  CHANGED="$CHANGED" python3 - "$pyproject" <<'PY'
import os, re, sys

path = sys.argv[1]
files = [f for f in os.environ["CHANGED"].splitlines() if f.strip()]
block = "only_mutate = [\n" + "".join(f'    "{f}",\n' for f in files) + "]"

source = open(path).read()
patched, n = re.subn(
    r"^only_mutate = \[.*?^\]", block, source, count=1, flags=re.S | re.M
)
if n == 0:
    # No dial to turn: append one to the section so the run is still scoped.
    patched = re.sub(
        r"^\[tool\.mutmut\]$", "[tool.mutmut]\n" + block, source, count=1, flags=re.M
    )
open(path, "w").write(patched)
PY

  # mutmut 3 copies the sources into ./mutants and runs there; a stale copy from
  # a previous scope would silently re-report yesterday's mutants.
  rm -rf mutants
  mutmut run
}

# NOT `|| true`: a run that could not start must not fall through to an empty
# results list that reads like a clean bill of health.
if ! run_mutmut; then
  echo
  echo "mutmut exited non-zero. That is NORMAL when mutants survived — read the"
  echo "list below. If it printed a usage or config error instead, nothing was"
  echo "mutated and there is nothing below to trust."
fi

echo
echo "== Surviving mutants (each one is a test that lied) =="
mutmut results
echo
echo "Inspect one with: mutmut show <id>   — then strengthen the assertion"
echo "that should have killed it, and re-run this script."
echo
echo "Not every survivor is a gap: a mutant that cannot change behaviour in any"
echo "reachable state (a getattr default for a setting base.py always defines, a"
echo "cache TTL whose key already carries the date) is equivalent, and killing it"
echo "costs an assertion about implementation — smell #6. Name the behaviour"
echo "first; if you cannot, leave the mutant and say why."

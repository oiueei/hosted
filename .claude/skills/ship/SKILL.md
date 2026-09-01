---
name: ship
description: Pre-commit checklist for OIUEEI — review changes, run backend and frontend tests, identify missing tests, update .md documentation, confirm branch is `development`, then commit in British English as co-author. Use when the user says they are ready to commit or ship work.
disable-model-invocation: true
---

# Ship — Pre-Commit Checklist

## Live Context

- Current branch: !`git branch --show-current`
- Working tree: !`git status --short`
- Changes since last commit: !`git diff HEAD --stat`

---

You are about to help the user ship their work. Work through each phase below in order. Do not skip any phase. Report clearly on what you find at each step.

## Phase 1 — Review Recent Changes

Understand what changed. Which range depends on the shape Phase 7 will find:

- **Uncommitted work in the tree** — `git diff HEAD`.
- **Work already committed this session** (the common case — see Phase 7A) — review the
  commits themselves with **`git diff @{push}..HEAD`**. The user drives every push in this
  repo, so "not yet pushed" *is* the work in flight — the same range `solid-testing` audits by
  default. **Not the last tag** (`$(git describe --tags --abbrev=0)..HEAD`): that is the whole
  release round including work already pushed and reviewed, which is `/prerelease`'s range,
  not this one. **Not `main..HEAD`** either: `main` is a release branch, so where it sits says
  nothing about what this session did — it can coincide with the push ref, and equally can not.

Then summarise:
- Which files were modified and why
- What features, fixes, or refactors were introduced
- Any obvious concerns (commented-out code, debug prints, TODO left in, hardcoded secrets)

## Phase 2 — Run Backend Tests

Run:
```
pytest -v --cov=core --cov-report=term-missing --cov-fail-under=96
```

- If tests fail, stop and report the failures to the user. Do not proceed to the commit.
- If coverage drops below the gate, stop and report it to the user.
- If all tests pass and the gate is met, report the result and continue.

> **The gate must match CI, and CI is the source of truth** — `.github/workflows/tests.yml`,
> mirrored in `CLAUDE.md`. It is a **ratchet**: it sits ~2 points under the suite's real
> coverage and is raised as coverage grows, so the number above goes stale by design. Check
> the workflow if in doubt, and never lower it here to make a run green. This file said `80`
> long after CI had moved to `95`, which meant a `/ship` could report success on a commit the
> build would reject — the one failure mode a pre-commit checklist exists to prevent.

## Phase 3 — Run Frontend Tests

Run:
```
cd frontend && npm run test:coverage
```

- If tests fail, stop and report the failures to the user. Do not proceed to the commit.
- If all tests pass, report the result and continue.

> **`test:coverage`, not `test`** — that is what CI runs. The bare `npm test` skips coverage
> entirely, so the frontend ratchet (statements/branches/functions/lines) is never checked and
> a regression ships green. The thresholds live in `frontend/vite.config.js` under
> `coverage.thresholds`, so the command **enforces them itself** and fails on its own: there
> are no numbers to compare by hand here. They are a ratchet like the backend's — raise as
> coverage grows, never lower to pass.

## Phase 4 — Check for Missing Tests

Review the changed files from Phase 1 and evaluate:

**Backend** — for each new or modified view, serializer, service, or model method:
- Is there a corresponding unit or integration test in `core/tests/`?
- Does the test cover the main happy path and at least one error path?

**Frontend** — for each new or modified component or hook:
- Is there a corresponding Vitest test?

List any gaps you find. If there are gaps, ask the user whether they want to add tests now before committing, or ship anyway with a note.

## Phase 5 — Check .md Documentation

Review the following documentation files against the changes made. Update any file whose content is now out of date:

- `README.md` — project overview, environment variables, API endpoints
- `core/models/CLAUDE.md` — model fields, business rules, methods
- `core/views/CLAUDE.md` — endpoint definitions, permissions, request/response formats
- `core/serializers/CLAUDE.md` — serializer fields and patterns
- `core/services/CLAUDE.md` — service logic and email patterns
- `frontend/CLAUDE.md` — React routes, pages, components
- `DESIGN.md` — design principles (rarely needs updating)

For each file, state clearly: **up to date** or **updated** (with a brief summary of what changed).

## Phase 6 — Confirm Branch

Verify the current branch is `development`. If it is not, stop and warn the user before proceeding.

## Phase 7 — Commit

Once all phases above are green (or the user has explicitly approved any exceptions). There
are two shapes here, and **this phase is not always a commit**.

### A — The tree is already clean

This repo commits **one concern per commit, as each lands**, so a session that worked that way
arrives here with nothing staged. That is the convention working, not a step skipped: a commit
made the moment its concern was finished and its suite was green is better evidence than one
assembled at the end from whatever the tree happened to hold.

So commit nothing. Confirm the tree is clean, list the commits the session produced
(`git log --oneline <range>`), and say plainly that Phase 7 was a no-op. Phases 1–6 are the
value of `/ship` in this case — they are the verification, not the paperwork around a commit.

### B — There are uncommitted changes

1. **Split by concern first, then stage.** One concern per commit, *not* one commit per
   session. If the tree holds two unrelated concerns, that is two commits, staged separately.
   A commit mixing them cannot be reverted without dragging the other out with it, which is
   the entire reason the convention exists.
2. **Stage explicitly**: `git add <paths>` — never `git add -A` blindly. Check `git status`
   between commits so nothing rides along uninvited.
3. **Keep the lockstep.** Docs (`README.md`, the `CLAUDE.md` files, `HEROKU.md`), seed data
   and **all three locales** (`ca`/`en`/`es`) travel in the *same* commit as the change they
   describe. A doc update landing one commit later means the earlier commit was wrong at the
   moment it was made, and a locale landing later means a language was briefly broken.
4. **Write the message in British English:**
   - Imperative subject (e.g. "Add", "Fix", "Update", not "Added"), ≤ 72 characters
   - A body explaining *what* changed and *why* — the why is the part the diff cannot show
   - The co-author trailer, composed **from the rules in `CLAUDE.md` §Commit
     attribution and nowhere else** — not from a previous commit, whose trailers
     may be wrong (that section says which ones and why). The short version: the
     live model's own name and version, no parenthesis unless it is `(1M context)`,
     `via Claude Code` only for non-Anthropic models, and the email by provider.
     ```
     Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
     ```
     Ask rather than guess if any part of the line is unclear.
   - **No "Para revisar (CA)" block** — visual-QA notes go in the chat, never in the message.
5. Run each commit using a HEREDOC to preserve formatting.
6. Confirm with `git log --oneline -<n>`, where *n* is the number of commits just made.

**Pushing is never part of this.** `/ship` commits; the push, the merge, the tag and the
deploy are the user's, on every branch including `development`. Do not offer to push as a
next step — say what is committed and stop there.

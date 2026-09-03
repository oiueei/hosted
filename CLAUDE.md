# OIUEEI - Development Guide

## Project Conventions

- **Single Django app**: All code lives in `core/`
- **Settings**: Split into `base.py`, `development.py`, `production.py` under `config/settings/`
- **Code style**: Ruff (100-char lines) — `ruff check` (lint + import sort) and `ruff format`; replaces black/isort/flake8. Pre-commit hooks in `.pre-commit-config.yaml` (run `pre-commit install`).
- **Test structure**: `core/tests/unit/`, `core/tests/integration/`, `core/tests/scenarios/`
- **Coverage minimum**: backend **96%**, frontend **87/79/79/89** (statements/branches/functions/lines), both enforced by CI. The frontend numbers live in `frontend/vite.config.js` (`test.coverage.thresholds`), which is the one that CI actually enforces — raise them there and here in the same commit. They are **ratchets, not targets** — each sits ~2 points under the suite's real coverage so a genuine regression is visible. Raise them as coverage grows; never lower one to make a red build pass. New code owes tests that name a behaviour, not lines.
- **All PKs**: 6-character alphanumeric codes generated via `secrets.choice()` (not auto-increment)
- **Dependencies are pinned, not ranged**: `requirements/*.txt` uses `==` on every direct dependency, so the `pip-audit` run in CI and the Heroku build resolve the same versions — a range let a release published between them reach production unaudited. Transitives are still unpinned; a full `pip-compile --generate-hashes` lock has to be resolved on Python 3.12 (`.python-version`), not on whatever is local. CI audits **both** `production.txt` and `development.txt`. Frontend: `npm ci` + `package-lock.json` already give this, gated by `frontend/scripts/audit-gate.mjs`.
- **Emails**: All user content escaped via `django.utils.html.escape()`
- **String length in migrations**: SQLite (local) does NOT enforce `CharField(max_length=N)` at the DB level — PostgreSQL (Heroku/production, **and CI**) does. Since the 2026-08 testing round CI runs the backend suite on Postgres (`DATABASE_URL` in `.github/workflows/tests.yml`), so an overflow now fails a build instead of reaching production — but a local `pytest` still won't see it. Always verify that seed data fits within the model's `max_length` before committing. Key limits: `headline` = 64, `description` = 256, `name` = 32, `email` = 64, `question` = 64, `answer` = 256, `location` = 32, `about` (User Markdown bio) = 2000, each `tags` label (Collection/Thing) = 32 (max 12 tags), `deposit_policy` (Collection) = 256.
- **Owner content can be multilingual**: on **Thing and Collection**, `headline`, `description` and each `tags` label may hold one text per language as inline JSON — `{"es": "Las cosas de mamá", "ca": "Les coses de mama"}` — and every reader sees theirs (`core.utils.parse_localized` / `resolve_localized`, `frontend/src/utils/localized.js`). Anything that isn't a strict `{lang: text}` map over `es`/`ca`/`en` renders **verbatim**, so an owner writing prose never notices. Consequently the limits above are **per language** and the *columns* are wider than them: Thing/Collection `headline` = 64 visible / 256 stored, `description` = 256 / 1024, tag label = 32 / 160 (JSONField), Collection `deposit_policy` = 256 / 1024. The serializer (`LocalizedHeadlineField` / `LocalizedTextField`) is what enforces the visible limit — the column no longer does. `Report.thing_headline` snapshots `Thing.headline`, so it tracks its width.
- **Demo data lives in a command, not migrations**: `python manage.py seed_demo` populates Lala/Lele/Lili/Lolo/Lulu and their collections. Idempotent (`update_or_create`). Fresh DBs start empty; run the command explicitly (also on Heroku: `heroku run --app <app> "python manage.py seed_demo"` — quote the inner command, otherwise the Heroku CLI intercepts inner flags like `--lang`/`--reset` as its own). Collection/thing text is always seeded in **all three languages at once** (inline `{es,ca,en}` localized maps, tag labels and `Collection.deposit_policy` included — the constants in `seed_data/common.py`); `--lang=en|es|ca` only picks the language of the plain-column text (user bios, FAQs), and `--reset` wipes demos before re-seeding. The shared structure lives in `seed_data/common.py` and each language's text in `seed_data/{lang}.py`, merged by `seed_demo.load_seed_data` (parity + length limits pinned by `core/tests/unit/test_seed_localized.py`). Don't add new demo data to migrations — edit the relevant `seed_data/*.py` and re-run. To add a new language, copy `en.py` → `{lang}.py` and translate only the text (keep the same codes/keys — the structure stays in `common.py`, respecting model max_length), then add the code to `SUPPORTED_LANGS` in `seed_demo.py`.

## Model selection

- **Session default: `opusplan`** (`~/.claude/settings.json`). Opus reasons in plan
  mode, Sonnet executes.
- **A code review runs on Opus, never Sonnet** — whether it is asked for in the
  chat or run through `/prerelease`. A review is judgement, not typing, and the
  session default puts Sonnet on everything that is not plan mode.
  - `/prerelease` pins it itself: `model: opus` in its SKILL.md frontmatter, which
    overrides the session model for the turn that invokes it and is not saved to
    settings. Verified against the official skills frontmatter schema, which
    accepts the same values as `/model`.
  - The **bundled** `/code-review` cannot be pinned this way: its frontmatter is
    not ours, `skillOverrides` controls visibility only, and shadowing the name
    with a local skill would replace the review itself rather than its model. Set
    the session model to Opus before invoking it.

## Commit attribution

Claude Code's own trailer is switched off (`"attribution": {"commit": ""}` in
`~/.claude/settings.json`), so the trailer below is the only one a commit carries.
There is exactly one format:

```
Co-Authored-By: <model name and version>[ (<context>)][ via Claude Code] <email>
```

- **The name comes from the live model**, read from whichever model is actually
  running: `Claude Opus 5`, `Claude Sonnet 5`, `GLM-5.2`. Never copied from a
  constant, a config file, or a previous commit — when a new version ships, the
  line must reflect it on its own.
- **The parenthesis is a closed list**, and today it holds one value: `(1M context)`.
  Omitted by default. Nothing else may go there — not the subject of the commit, a
  summary of the task, a date, a branch name, or an issue id. A new value is added
  by asking, not by inventing.
- **`via Claude Code`** is for models that are not Anthropic's. Claude models omit it.
- **The email comes from this table, by provider** — never from the model name, and
  it never carries a version:

  | Provider | Email |
  |---|---|
  | Anthropic (`Claude *`) | `noreply@anthropic.com` |
  | Z.ai (`GLM *`) | `noreply@z.ai` |

  A provider that is not in the table is a **stop and ask**. Do not infer an
  address from the model name or a domain, and never use a provider's real contact
  mailbox — those are people, not co-author identities.
- **One line per model that genuinely took part.** Opus planned and Sonnet executed
  means two lines. A phase whose model is uncertain is omitted, not guessed at, and
  never filled in for symmetry.
- **Never copy a trailer from git history.** The body's style is worth imitating;
  the trailers are not. Commits from August 2026 carry a wrong format — a task
  descriptor in the parenthesis and invented addresses of the `opus5@anthropic.com`
  shape. They are a known error, left in place deliberately because the history is
  not being rewritten, and they are not a precedent.

Valid:

```
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Co-Authored-By: GLM-5.2 (1M context) via Claude Code <noreply@z.ai>
```

When in doubt about how to compose the line, ask rather than decide.

## Project Documentation

For complete information about OIUEEI — project structure, tech stack, API endpoints, development setup, environment variables, security measures, and roadmap — see [`README.md`](README.md).

## Detailed Models Documentation

For complete field-by-field documentation, business rules, methods, and reverse relations for each model, see [`core/models/CLAUDE.md`](core/models/CLAUDE.md).

## Detailed Views Documentation

For endpoint definitions, permissions, request/response formats, and business logic for each Django view, see [`core/views/CLAUDE.md`](core/views/CLAUDE.md).

## Detailed Serializers Documentation

For serializer patterns (security fields, prefetch-aware computed fields, asset URLs), naming conventions, and field-by-field documentation for each serializer, see [`core/serializers/CLAUDE.md`](core/serializers/CLAUDE.md).

## Detailed Services Documentation

For booking business logic (atomic transactions, row-level locking) and centralised email service (XSS prevention, dual format, action links), see [`core/services/CLAUDE.md`](core/services/CLAUDE.md).

## Frontend Documentation

For React routes, pages, tech stack, Vite configuration, and authentication flow, see [`frontend/CLAUDE.md`](frontend/CLAUDE.md).

## Design Guidelines

When designing or reviewing any frontend view, component, or copy, consult [`DESIGN.md`](DESIGN.md) and apply all nine principles. Use the checklist at the end of that document before considering any view complete.

# OIUEEI — the www.oiueei.com deployment

This repository is the **running deployment** behind [www.oiueei.com](https://www.oiueei.com):
the application from [`oiueei/standalone`](https://github.com/oiueei/standalone) plus the thin
service layer one operator adds to run it as a service.

## You are probably looking for the standalone repo

Everything about OIUEEI itself — what it is, the data model, the API, the tech stack, how to
**self-host your own**, the environment variables, the security measures, the roadmap — lives
in **[`oiueei/standalone`](https://github.com/oiueei/standalone)** and its `README.md`,
`SELF_HOSTING.md`, `HEROKU.md`, `CONTRIBUTING.md`, `DESIGN.md` and the `CLAUDE.md` files. This
repo does not repeat any of it, and it is not the one to fork or file issues against.

The licence is the same — **EUPL-1.2**, see [`LICENSE`](LICENSE), unchanged from upstream.

## What this repo adds on top of upstream

Only what belongs to *this* operator's service — never a change to shared behaviour:

| Addition | What it is |
|---|---|
| [`hosted/`](hosted/) | The service-layer Django app: the open sign-up door (`/api/v1/auth/pop-in/`), the request-access form, the creator-validation model, the weekly operator report. See [`hosted/README.md`](hosted/README.md). |
| `frontend/src/deployment/` | The SPA half — the `/popin`, `/welcome` and `/faq` pages and their copy, replacing the empty stubs upstream ships. |
| [`DESIGN_HOSTED.md`](DESIGN_HOSTED.md) | Design rules for those surfaces. Adds to `DESIGN.md`, never overrides it. |
| `frontend/src/legal/{ca,en,es}.js` | The full RGPD/LSSI legal notice. The operator's identity is injected from `VITE_LEGAL_OPERATOR` / `_NIF` / `_ADDRESS` at build time — `frontend/scripts/check-legal-env.mjs` enforces it, so the tax ID and address are never committed. |
| `config/settings/*.py`, `requirements/production.txt` | Sentry (EU region, PII scrubbed) and the settings that mount `hosted/`. |
| `.github/workflows/hosted.yml` | A coverage floor for `hosted/`, which the shared workflow cannot give it. |
| `package.json` | `heroku-postbuild` fetches the Curiosa font (its licence forbids redistributing it, so it is never committed — see `HEROKU.md`). |

## Keeping in sync with upstream

This repo shares history with `oiueei/standalone` — `origin` points there. When the product
moves:

```bash
git fetch origin
git merge origin/main
git push        # to hosted
```

Expect a conflict in `frontend/src/legal/{ca,en,es}.js` most times upstream touches the legal
text: keep this repo's version and reapply any structural change by hand. `config/settings/*.py`,
`frontend/package.json` and `requirements/production.txt` conflict only when upstream edits the
same lines. This file is marked `merge=ours` in `.gitattributes` so it is left alone
automatically — run `git config merge.ours.driver true` once in this clone for that to take
effect.

## Deploying

See [`HEROKU.md`](HEROKU.md) for the full setup. On top of the upstream config vars this
deployment also needs `VITE_LEGAL_OPERATOR` / `_NIF` / `_ADDRESS`, `SENTRY_DSN` (an EU-region
DSN — `…ingest.de.sentry.io`), `STATS_EMAIL` and `CURIOSA_FONT_URL`.

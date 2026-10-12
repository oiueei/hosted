# OIUEEI hosted - Agent guide

This repository is the **hosted layer**: the "mini SaaS" that runs www.oiueei.com on Heroku, on top of
`oiueei/standalone`. It only ever **adds** to the product; the product itself (`core/`, the shared
frontend, `CLAUDE.md`) is standalone's. Read `hosted/README.md` for what this deployment did with the
extension points described in `SELF_HOSTING.md`.

## What a session here may change

- `hosted/` (the Django app: open sign-up door, creator vetting, weekly operator report)
- `frontend/src/deployment/` — including `index.js`, whose **values** are this deployment's; its
  **contract** (an export added, renamed or reshaped) is upstream's and changes in `oiueei/standalone`
  first.
- `frontend/src/legal/` (the operator's identity and legal text)
- the hosted parts of `config/settings/*.py`
- `core/tests/**/test_hosted_*`
- `.github/workflows/hosted.yml`
- `DESIGN_HOSTED.md`, and this repository's own README and CONTRIBUTING

## What it may not

- **A product fix is not made here.** If the changed files are under `core/` or in the shared frontend,
  describe the fix for `oiueei/standalone` (`development`) instead; it reaches this repository by
  merging. A `core/` change committed here is invisible to the sync and has to be re-applied by hand
  forever (`hosted/README.md`, "Where a fix belongs").
- **`.github/workflows/tests.yml` is not edited here.** It is the same file in both repositories, and
  here it is the deploy gate (Heroku deploys with "wait for CI"). A hosted-only edit would conflict in
  every merge; what is specific to this deployment goes in `hosted.yml`.
- **Never push this repository, or any of its branches, to `oiueei/standalone`.** Nothing that is
  reachable only from here belongs in the public product repository.

## Working rules

- The git author is the maintainer, never the model. The model appears only in the `AI-assistant:`
  trailer (see `CLAUDE.md`, "Commit attribution").
- An agent commits on its branch and stops there: no push, merge, tag or deploy.
- Confirm the current branch before editing: `legal/` and the deployment settings differ between
  branches.

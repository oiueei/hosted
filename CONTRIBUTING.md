# Contributing to OIUEEI

Thanks for looking. This file exists so nobody spends an afternoon on work that
cannot be merged.

## Pull requests are closed for now

**OIUEEI is not accepting pull requests at this time.** This is not a comment on
anyone's code — it is a deliberate decision while the project is still finding
its footing, and it comes down to two things:

1. **One maintainer.** OIUEEI is built and run by one person. Reviewing,
   testing and maintaining third-party code is real, ongoing work, and right now
   that time goes into finishing the product.
2. **Licensing is not settled.** The maintainer currently holds all copyright in
   the codebase, which keeps the project's licensing options open. Accepting
   outside contributions without a contributor agreement in place would close
   those options permanently. Until that agreement exists, the honest answer is
   "not yet".

If and when pull requests open, contributors will be asked to sign a Contributor
License Agreement. That will be announced here, in this file. No timeline is
promised.

## What is welcome, today

**Issues.** All of these are genuinely useful and cost you nothing but the time
to write them up:

- **Bug reports.** What you did, what you expected, what happened instead.
- **Self-hosting problems.** If `SELF_HOSTING.md` left you stuck, that is a
  documentation bug and worth reporting.
- **Accessibility findings.** Keyboard traps, screen-reader problems, contrast
  failures, focus order. These are taken seriously — see the accessibility
  commitment in `DESIGN.md`.
- **Translation corrections.** The interface ships in Catalan, Spanish and
  English. None of the translations have been reviewed by a native speaker; if
  something reads wrong to you, please say so.
- **Questions about the license.** Ask. Getting this right matters more than
  getting it quickly.

**Please do not** open an issue that is a pull request in disguise — a full patch
pasted into the description raises exactly the copyright question this file is
trying to avoid. A clear description of the problem is more useful anyway.

## The bar, for when this changes

Written down now so it is not invented later, and so an issue can be argued
against something. These are the house rules the codebase already follows:

- **The service layer is the pattern.** Views are thin controllers; business
  logic lives in `core/services/`.
- **Tests come with the change.** Coverage floors are **ratchets, not targets**
  — they sit a couple of points under the suite's real coverage so a regression
  is visible, and CI fails the build below them. They are never lowered to make
  a build green. Each floor sits in a config file — `frontend/vite.config.js`
  for the frontend, `pyproject.toml` (`fail_under`) for the backend, which CI
  re-passes as `--cov-fail-under`. The house rule is that **a test names a
  behavior**; it does not cover lines.
- **HDS is the base.** UI changes extend Helsinki Design System components
  rather than replacing them, and deviate only where sharing-specific UX
  genuinely requires it.
- **An issue comes first.** For anything beyond a small fix, the approach is
  worth agreeing on before the code is written.
- **The data model is relational.** Model a relationship as a relationship — a
  `ForeignKey` / `ManyToManyField`, not a list of IDs in a `JSONField`.
  (JSONField is used on purpose for a few things — localized owner text, small
  fixed config lists — never as a stand-in for a table.) Include the migration.

## Security

**Do not report security issues in a public issue.** Email
`maintainer@oiueei.com` with what you found and how to reproduce it. You will get
an answer.

## About the license

OIUEEI is **source-available under the Business Source License 1.1**
(SPDX: `BUSL-1.1`) — every line of the product is public and auditable,
production self-hosting is allowed, and the code converts to the MIT License on
2 February 2030.

Two things that are commonly got wrong, so they are stated plainly here:

- **BUSL-1.1 is not an open source license**, and the license text says so
  itself. Please do not describe OIUEEI as open source. "Source-available" is
  the accurate word.
- **Self-hosting OIUEEI in production is allowed** — for your group, your
  cooperative, your organization, with real users. What the license reserves is
  offering OIUEEI to third parties as a hosted or managed service competing with
  the licensor's paid offering.

**There is no separate license for the design.** The CSS, the React components,
the color palettes and the brand files are all covered by the one license
above. There is no design subtree held apart, and no fork that takes "only the
code" — here the code *is* the design. The OIUEEI name and logo are trademarks,
and the license grants no rights in them.

The full terms are in [`LICENSE`](LICENSE). Third-party design components
(Helsinki Design System) retain their original MIT license.

## Contact

`maintainer@oiueei.com` — license questions, commercial licensing, security
reports, and anything that does not fit in an issue.

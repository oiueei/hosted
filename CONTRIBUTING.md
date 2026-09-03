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
2. **There is no contributor agreement yet.** The licence is settled — OIUEEI is
   EUPL-1.2 — but the maintainer still holds all copyright in the codebase, and
   that is what keeps the project's options open: relicensing later, or granting
   different terms to someone who needs them. Accepting outside contributions
   without a contributor agreement in place would close those options
   permanently for that code, with no way back — if a contributor moves on,
   there is no retroactive signature. Until that agreement exists, the honest
   answer is "not yet".

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

OIUEEI is licensed under the **European Union Public Licence v. 1.2**
(SPDX: `EUPL-1.2`) — an OSI-approved strong copyleft licence: every line of the
product is public and auditable, self-hosting in production is allowed, and
modifications you pass on — including by running them as a service — carry the
same licence.

Two things worth stating plainly:

- **The EUPL's copyleft reaches use over a network.** Running a *modified* copy
  as a service counts as distribution, so those changes are owed to your users
  under the same licence — the same as if you shipped them a binary. An
  unmodified deployment owes nothing beyond keeping the notices.
- **Self-hosting OIUEEI in production is welcome** — for your group, your
  cooperative, your organization, with real users. The licence asks for
  reciprocity, not a fee.

**There is no separate license for the design.** The CSS, the React components,
the color palettes and the brand files are all covered by the one license
above. There is no design subtree held apart, and no fork that takes "only the
code" — here the code *is* the design. The OIUEEI name and logo are trademarks,
and the license grants no rights in them.

The full terms are in [`LICENSE`](LICENSE). The EUPL is published by the
European Commission in 23 official languages of identical legal value, Spanish
among them. Third-party design components (Helsinki Design System) retain their
original MIT license.

## Contact

`maintainer@oiueei.com` — license questions, commercial licensing, security
reports, and anything that does not fit in an issue.

# OIUEEI — Design Guidelines for the Hosted Service

These are the design rules for the surfaces that exist **only on www.oiueei.com**: the
open sign-up door, the operator's "what is this" page, and the manual validation gate.

## How this document relates to `DESIGN.md`

`DESIGN.md` is the canon and this file never repeats it. All twelve principles — HDS
first, tone, minimalism, mobile first, WCAG AA, no dark patterns, performance, i18n,
user data is never a product, Koros + theeeme, black icons, the four breakpoints —
apply here **unchanged**. Nothing about a page changes because there is an operator
behind it; what changes is that there are more pages.

Two rules keep it that way:

1. **This file adds, it never overrides.** This deployment only ever *adds* files the
   public repo does not have — that is what makes an upgrade a merge instead of an
   argument, and it is why there is no second `DESIGN.md`. Editing the canonical one
   here would put a prose conflict in the path of every design round upstream.
2. **A contradiction is a bug upstream, not a local exception.** If a hosted surface
   ever seems to need a principle broken, the principle was written as universal when
   it isn't. Fix it in `DESIGN.md` — name the part that depends on the deployment —
   and leave this file adding only what genuinely has nowhere else to live.

## 1. `/popin` — the demo door

**It is an acquisition funnel, not a showcase.** This is the piece most easily
described wrong, and the description drives the design: `/popin` creates a **real,
permanent account**, drops that person into the shared demo collections, and mails them
a magic link. Everything they create afterwards is real product, untouched by a
`seed_demo --reset`.

- **Never design it as "try it without signing up."** It *is* signing up. Copy that
  implies a throwaway session is the dark pattern DESIGN §6 exists to forbid, and it
  would be lying about an account that outlives the visit.
- **The demo data must say it is demo data.** A visible banner or alert — "⚠️ This is a
  demo" — wherever seed content is on screen. A product whose brand is honesty cannot
  let anyone mistake the showcase for the shop.
- **And it must be equally clear what is not demo.** The same person's own collections
  are real and survive the reset. One line where it matters beats a warning nobody can
  act on.
- **The demo collections are shared with everyone who pops in, and are reset by hand.**
  No copy anywhere may suggest privacy, permanence or ownership for anything left
  there.
- **It depends on the seed.** Without `seed_demo`, `/popin` and the sample collections
  land on empty pages or a 404 — so any design that assumes content must degrade to an
  honest empty state, not a broken one.

## 2. `/welcome` — the operator's "what is this"

**It is one operator's speech, not the product's definition.** That is precisely why it
is not in the public repo: what OIUEEI *is* gets told in the `README`; what *this
service* is gets told here.

- Claims about the software must be checkable against the public repo. Claims about the
  service — who runs it, where the data lives, what is promised — belong to the
  operator and must not contradict `/legal`, which is the page the privacy claims tell
  people to go and check.
- It is what the footer's about link and Home's empty state point at (`aboutPath`,
  supplied through `frontend/src/deployment/`). Shared components must never assume the
  page exists; upstream they render one link fewer, and that is correct, not degraded.

## 3. `/request-access/` and the approval notice — the validation gate

Creating `COMMUNITY`, `LEND` or `RENT` needs a person to say yes. The design job is to
make a manual gate feel like an honest "not yet" rather than a wall.

- **The notice under the control is a quiet line, not an error.** It names what is
  withheld in the same words the form uses and links to where to ask. It lives in the
  public repo (`ApprovalNotice`) because the mechanism is generic; with nothing
  withheld it never draws.
- **It must never read as a paywall tease.** The gate is a person reading a request —
  not a plan, not a tier, not an upgrade. No pricing language on any of these surfaces,
  including the ones that would only hint at it.
- **Do not simplify the form into a one-click "request access" button.** The written
  answer *is* the filter: who you are, and what collection you intend to create. This
  runs against the usual reduce-friction reflex, which is exactly why it is written
  down — the friction is the feature.
- **A refusal says the slots are currently full, and offers no appeal surface.** Design
  no debate UI around it. The door is a person's judgement, and it must not become a
  tribunal.
- **Withdrawal is three warnings and an export, never a slammed door** (30 days, 1 week,
  3 days, then their data in hand). If any of it ever gets a screen, it inherits that
  shape.
- **Guests are never touched by this.** Anyone invited to a collection browses, asks,
  reserves and contributes with no validation at all. Gate copy must not appear on a
  single guest-facing surface.
- It is a Django page **outside the SPA**, so it gets none of the theeeme/Koros
  machinery for free. It still owes the same visual language and the same WCAG AA floor
  as far as a server-rendered page can carry them.

## 4. What is deliberately not in this document

Nothing about **prices, plans, limits or trial periods**. The service is free and there
is no paid tier — the FAQ and the legal terms say so — so there is no pricing surface to
design. If that ever changed, the work would add sections here; it would not change
`DESIGN.md`.

## Checklist — hosted surfaces only

Run this **after** the twelve checks in `DESIGN.md`, not instead of them:

1. Does anything showing seed data say, visibly, that it is a demo?
2. Does any copy imply `/popin` is a throwaway session rather than a real account?
3. Does any demo surface imply privacy or permanence for what is left there?
4. Does `/welcome` claim anything about the software the public repo cannot back, or
   anything about the service that `/legal` does not?
5. Does any shared component assume a deployment page (`aboutPath`, the open door)
   exists?
6. Does the approval notice read as "not yet" rather than as a plan you could buy?
7. Is the request form still asking for a written answer?
8. Does any gate copy leak onto a guest-facing surface?

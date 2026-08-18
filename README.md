## What is OIUEEI?

A source-available web application (BUSL 1.1 — every line of the product public and auditable; MIT from 2030; self-hosting in production is allowed, offering it as a competing hosted service is not) for people to share their belongings with friends and others around. Users can create collections (things to lend, rent, give away or sell) and share them with friends who can then reserve items or ask questions.

No ads, no tracking of any kind, no third-party code running in your browser — and no cookie banner, because there is nothing to consent to. Each of those claims comes with a way to check it: **[→ Privacy](#privacy)**.

## Authorship & Development

OIUEEI is designed and led by Carlos Alberto, a designer, and co-written with [Claude Code](https://claude.ai/code), Anthropic's command-line coding assistant. UI and UX design decisions, product scope, tone and voice, and the choice to build on HDS are Carlos Alberto's; Claude carries a large share of the Django, DRF, and React implementation under direction. Every commit involves Claude, is reviewed before it ships, and is signed with a `Co-Authored-By: Claude` trailer — the contribution history is fully transparent.

## Try it (and tell me what breaks)

OIUEEI is in **alpha**: nothing is finished, nothing is at 100%, and you'll find rough edges. That's exactly why your hands on it would help.

**To see a populated OIUEEI in about a minute**, run it locally and sign in as one of the seeded people — no signup, no email server:

```bash
python manage.py seed_demo          # Lala, Lele, Lili, Lolo, Lulu and their collections
python manage.py runserver          # then, in frontend/: npm run dev
```

Open `http://localhost:3000/login`, enter **`lala@mail.com`**, and the magic link is **printed in the terminal running Django** (development uses the console email backend). Click it and you are in, with collections, things and every sharing mode already populated.

What I'm looking for is honest feedback from people willing to poke at it: things that confuse you, flows that break, words that don't make sense, design decisions you'd push back on. If something annoys you, that's signal.

**[→ Tell me what you found](https://tally.so/r/A76Xkz)** (2 minutes, no signup needed)

## Tech Stack

- **Backend**: Django 5.x + Django REST Framework
- **Frontend**: React (same repo, work in progress)
- **Auth**: Magic link authentication (passwordless for users, password enabled for admin access)
- **Database**: SQLite (dev), PostgreSQL (prod via `dj-database-url`)
- **Deployment**: Heroku (Procfile + `.python-version` included)
- **Static files**: WhiteNoise
- **PWA**: installable web app manifest + icons ("Add to Home Screen"); no service worker yet
- **Scheduled tasks**: one daily Heroku Scheduler job chains `expire_bookings`, `cleanup_rsvps`, `close_transfers`, `send_reminders` and `send_digests` (see [HEROKU.md](HEROKU.md))

## UI & Design System

OIUEEI's user interface is built on top of the [Helsinki Design System (HDS)](https://hds.hel.fi/), an open-source design system created by the City of Helsinki. OIUEEI consumes HDS at multiple levels:

- **React components** — via [`hds-react`](https://github.com/City-of-Helsinki/helsinki-design-system/tree/master/packages/react)
- **Design tokens** — colours, spacing, typography, and breakpoints from [`hds-design-tokens`](https://github.com/City-of-Helsinki/helsinki-design-system/tree/master/packages/design-tokens)
- **Core styles** — base CSS from [`hds-core`](https://github.com/City-of-Helsinki/helsinki-design-system/tree/master/packages/core)

### What I customise

HDS is designed for City of Helsinki services, so I adapt it to fit OIUEEI's context:

| Layer | HDS baseline | OIUEEI adaptation |
|---|---|---|
| Brand colours | Helsinki blue/black palette | Custom palette reflecting OIUEEI identity |
| Typography | HDS type scale | Same scale, different primary typeface (Curiosa) |
| Components | Used as-is where possible | Extended or wrapped when sharing-specific UX is needed |
| Layout & spacing | HDS grid and spacing tokens | Followed as-is |
| Icons | HDS icon set | Supplemented with domain-specific icons |

Our goal is to **stay as close to upstream HDS as possible** to benefit from accessibility audits, updates, and community contributions, while making only the changes strictly necessary for our use case.

### Why HDS?

- **Accessibility built-in** — All HDS components are WCAG 2.1 AA audited.
- **Open source (MIT)** — Fully compatible with OIUEEI's source-available licence (BUSL 1.1).
- **Production-proven** — Used across hundreds of City of Helsinki digital services.
- **React-native support** — Aligns with our tech stack (React + Vite).

## Project Structure

```
config/
  settings/
    base.py          # Shared settings
    development.py   # Dev overrides (SQLite, DEBUG=True)
    production.py    # Prod overrides (PostgreSQL, security headers)
  urls.py            # Root URL config (admin at /oiueei-admin/)
  wsgi.py            # WSGI entry point (defaults to production)
core/
  models/            # User, Collection, Thing, FAQ, Theeeme, RSVP, BookingPeriod
  views/             # Auth, collections, things, bookings, FAQ, users
  serializers/       # DRF serializers per model
  services/          # Business logic layer
    email_service.py   # All email composition and sending (categorised opt-out pipeline)
    booking_service.py # Accept/reject booking logic (transaction.atomic)
  permissions.py     # Custom DRF permissions (IsThingOwner, IsCollectionOwner)
  validators.py      # Input validation (image IDs, headlines, etc.)
  utils.py           # ID generation, client IP, Cloudinary URLs
  pagination.py      # StandardResultsPagination (max 100)
  management/
    commands/
      expire_bookings.py  # Batch expire stale PENDING bookings
      cleanup_rsvps.py    # Delete expired RSVPs (24h+)
      close_transfers.py  # Close overdue loan transfers
      send_reminders.py   # Daily booking/delivery reminders
      send_digests.py     # Weekly/monthly digest emails
      backfill_events.py  # One-off: seed the Event log from existing rows
      seed_demo.py        # Populate demo data (idempotent; --lang=en|es|ca)
      seed_data/
        common.py         # structure + localized tag constants (non-translatable)
        en.py             # English demo content
        es.py             # Spanish demo content
        ca.py             # Catalan demo content
  tests/
    unit/            # Model, serializer, validator, security tests
    integration/     # View and booking integration tests
    scenarios/       # End-to-end user flow tests
```

## Data Models

| Model | Purpose |
|-------|---------|
| **User** | Custom user with `code` as PK (6-char alphanumeric). Magic link auth, no passwords. `notify_activity` and `notify_news` (both default on) control Cat. 2 / Cat. 3 email delivery (magic links and invitations are always sent). News is narrowed per group by `Collection.digest_muted`, so silencing one noisy collection never costs you the transactional mail — which is what keeps an on-by-default news flag off the DESIGN §6 dark-pattern list. Optional profile extras: `about` (free Markdown bio) and `photo` (Cloudinary profile photo, exposed as `photo_url`) |
| **Collection** | Lists of things owned by a user. Shared via M2M `invites`. FK to `Theeeme`. `allow_member_proposals` (default on) decides whether members may recommend new guests — the owner still approves every one, and nothing reaches the proposed person before that. Mode: PROPRIETARY (only owner adds things) or COMMUNITY (invited users can add their own things) — mode decides WHO may add a thing, never which types. `share_token` is a 22-char URL-safe bearer credential generated on demand for the public `/share/{token}` link — never exposed in any read serializer. `tags` is an owner-defined free-text tag vocabulary (max 12) that the collection's things can be tagged with; removing a tag here cascade-strips it from those things. |
| **Thing** | Items in collections. Types: GIFT_THING, SELL_THING, RENT_THING, LEND_THING. `status` controls both visibility and reservation state (ACTIVE/TAKEN/INACTIVE). `gallery` JSONField holds up to 8 additional photos (exposed as `gallery_urls`), shown as an image carousel. For date-based types (LEND/RENT), `available_today`/`next_available` expose live availability computed from the booking calendar. `tags` holds owner-defined labels chosen from the collection's `tags` vocabulary, shown as HDS Tags on the card and detail |
| **FAQ** | Questions/answers about things. FK to Thing and User (questioner) |
| **Theeeme** | Colour palettes (6 HDS colour token names) for customising collections |
| **RSVP** | One-time-use tokens (24h expiry) for auth and email actions. FK to User |
| **BookingPeriod** | Unified booking model for all thing types (72h expiry). FKs to Thing, User (requester), User (owner) |
| **Event** | Append-only first-party analytics log. Text **snapshots** (`actor_code`/`collection_code`/`thing_code`), not FKs, so rows outlive hard-deleted objects. `kind` covers the tracked actions (user joined, collection/thing added/removed, member joined/left, FAQ asked, hold requested/accepted). Written by one-line instrumentation next to the notification/email each action already fires; read only by whatever reporting the deployment runs over it. Never exposed to users |
| **DailyActivity** | One `(user, date)` row per user per active day, written by `DailyActivityMiddleware` (cache-gated to ≤1 DB write per user per day). Powers WAU/MAU and retention. Records less than the web-server logs already hold and never leaves our DB |

## Key Relationships

All relationships use proper Django ForeignKey and ManyToManyField:

- `Collection.owner` -> FK to User
- `Collection.things` -> M2M to Thing (via `collection_things` table)
- `Collection.invites` -> M2M to User (via `collection_invites` table)
- `Collection.theeeme` -> FK to Theeeme (PROTECT)
- `Thing.owner` -> FK to User
- `Thing.deal` -> M2M to User (via `thing_deals` table)
- `FAQ.thing` -> FK to Thing
- `FAQ.questioner` -> FK to User
- `BookingPeriod.thing_code` -> FK to Thing
- `BookingPeriod.requester_code` -> FK to User
- `BookingPeriod.owner_code` -> FK to User
- `RSVP.user_code` -> FK to User

## API Endpoints

### Auth & RSVP Actions
| Method | URL | Description |
|--------|-----|-------------|
| POST | `/api/v1/auth/request-link/` | Request magic link (rate limited: 5/min) |
| POST | `/api/v1/auth/join/` | Join a collection you were pointed at — by `share_token` (an owner's `/share/{token}` link) or by the `collection_code` of a PUBLIC one — and get a magic link. **Creates nothing without a valid target**, and answers identically either way (rate limited: 5/min per IP, 5/h per email) |
| GET / POST | `/api/v1/auth/verify/{rsvp_code}/` | Verify magic link / process an RSVP action (rate limited: 10/min). Booking accept/reject only **preview** on GET and require a **POST** to commit, so an email link-scanner or prefetch can't auto-decide a hold; login/invite actions resolve on GET |
| GET / POST | `/api/v1/rsvp/{rsvp_code}/` | Alias for verify endpoint |
| POST | `/api/v1/auth/refresh/` | Rotate access/refresh tokens via HttpOnly cookies |
| GET | `/api/v1/auth/me/` | Get authenticated user, plus a **`capabilities`** block — `{collection_modes, thing_types, request_url}`, what this deployment lets them create (see [STANDALONE_HOSTED.md](STANDALONE_HOSTED.md)). It is the same `CreatorPolicy` answer the create endpoints refuse with, so a client cannot offer what the API would reject; upstream it lists everything and `request_url` is `null` |
| POST | `/api/v1/auth/logout/` | Log out (clears auth cookies) |
| POST | `/api/v1/auth/delete-account/` | Request account deletion (rate limited: 3/h): emails a 24h single-use confirmation link; the deletion itself commits via a POST on the verify endpoint (GET only previews) |

### Users
| Method | URL | Description |
|--------|-----|-------------|
| GET | `/api/v1/users/{user_code}/` | View profile (requires collection connection) |
| PUT | `/api/v1/users/{user_code}/` | Update own profile (name, headline, `about` Markdown bio, `photo`, koro, theeeme, `notify_activity`, `notify_news`) |
| GET | `/api/v1/notifications/token/{token}/` | Read `notify_activity`/`notify_news` via signed token (no login required; linked from every Cat. 2/3 email footer) |
| PATCH | `/api/v1/notifications/token/{token}/` | Update `notify_activity`/`notify_news` via signed token |
| POST | `/api/v1/digest/mute/{token}/` | One-click unsubscribe from **one** collection's digest, via the signed link in that digest's footer (no login). POST-only so an email link-scanner can't unsubscribe anyone |

### Collections (ModelViewSet + Router)
| Method | URL | Description |
|--------|-----|-------------|
| GET | `/api/v1/collections/` | List own collections |
| POST | `/api/v1/collections/` | Create collection |
| GET | `/api/v1/collections/{code}/` | View collection (owner or invited) |
| PUT | `/api/v1/collections/{code}/` | Update collection (owner only) |
| DELETE | `/api/v1/collections/{code}/` | Delete collection (owner only) |
| POST | `/api/v1/collections/{code}/add-thing/` | Add thing to collection (owner; invited users in COMMUNITY mode) |
| POST | `/api/v1/collections/{code}/remove-thing/` | Remove thing from collection (owner; thing owner in COMMUNITY mode) |
| POST | `/api/v1/collections/{code}/invite/` | Invite user (owner only, resend-safe) |
| DELETE | `/api/v1/collections/{code}/invite/` | Remove invitee (owner only) |
| POST | `/api/v1/collections/{code}/share-link/` | Generate or rotate the public share token (owner only). Returns `share_url` and `share_token`. Pass `{"rotate": true}` to force a fresh token. Rate limited: 30/h. |
| DELETE | `/api/v1/collections/{code}/share-link/` | Revoke the public share token (owner only) |
| GET | `/api/v1/invited-collections/` | List collections where invited |
| GET | `/api/v1/my-invitations/` | List my pending collection invitations |
| POST | `/api/v1/collections/{code}/leave/` | Leave a collection you're invited to (self-unlink) |
| POST | `/api/v1/collections/{code}/invite/propose/` | Members only: recommend a guest to the owner. Nothing reaches the proposed address until the owner approves. Rate limited: 30/day |
| POST | `/api/v1/proposals/{code}/{approve\|reject}/` | The owner's answer to a member's recommendation (owner only) |
| POST | `/api/v1/collections/{code}/digest/` | Members only: silence or un-silence this collection's digest (`{"muted": true\|false}`). Rate limited: 30/h |
| POST | `/api/v1/collections/{code}/invite/bulk/` | Bulk-invite guests from a CSV (owner only, rate limited: 5/h) |
| GET | `/api/v1/collections/{code}/stats/` | Download a 90-day activity CSV (owner only) |
| POST | `/api/v1/collections/{code}/broadcast/` | Send a message to all invitees (owner only) |
| POST | `/api/v1/collections/{code}/things/bulk/` | Bulk-create things from a CSV (rate limited: 10/h) |

### Things (ModelViewSet + Router)
| Method | URL | Description |
|--------|-----|-------------|
| GET | `/api/v1/things/` | List own things |
| POST | `/api/v1/things/` | Create thing |
| GET | `/api/v1/things/{code}/` | View thing (owner or invited) |
| PUT | `/api/v1/things/{code}/` | Update thing (owner only) |
| DELETE | `/api/v1/things/{code}/` | Delete thing (owner only) |
| POST | `/api/v1/things/{code}/request/` | Request reservation (invited only) |
| GET | `/api/v1/things/{code}/calendar/` | View booking calendar (any thing — bookings without dates are listed too) |
| GET | `/api/v1/things/{code}/transfers/` | View transfer history and stats (Loan Chain) |
| POST | `/api/v1/things/{code}/activate/` | Reactivate an inactive thing (owner only) |
| POST | `/api/v1/things/{code}/hide/` | Set an active thing to inactive (owner only) |
| POST | `/api/v1/things/{code}/report/` | Report a listing anonymously (logged-in non-owners) |
| GET | `/api/v1/invited-things/` | List things from invited collections (paginated). Backs the frontend's `/shared` page — everything your groups are sharing, in one place |

### Bookings
| Method | URL | Description |
|--------|-----|-------------|
| GET | `/api/v1/my-bookings/` | List my booking requests (with thing headline, owner name) |
| GET | `/api/v1/owner-bookings/` | List bookings for my things (with requester name) |
| POST | `/api/v1/bookings/{code}/accept/` | Accept a pending booking (owner only) |
| POST | `/api/v1/bookings/{code}/reject/` | Reject a pending booking (owner only) |
| POST | `/api/v1/bookings/{code}/cancel/` | Cancel own pending booking (requester only) |

### FAQ
| Method | URL | Description |
|--------|-----|-------------|
| GET | `/api/v1/things/{code}/faq/` | List FAQs for a thing |
| POST | `/api/v1/things/{code}/faq/` | Ask question (invited users only, not owner) |
| GET | `/api/v1/faq/{code}/` | View FAQ |
| POST | `/api/v1/faq/{code}/answer/` | Answer FAQ (owner only) |
| POST | `/api/v1/faq/{code}/hide/` | Hide FAQ (owner only) |
| POST | `/api/v1/faq/{code}/show/` | Show FAQ (owner only) |

### Other
| Method | URL | Description |
|--------|-----|-------------|
| GET | `/api/v1/inbox/` | List in-app notifications for the current user |
| DELETE | `/api/v1/inbox/{code}/` | Dismiss an in-app notification |
| POST | `/api/v1/upload/signature/` | Get a signed Cloudinary upload signature (rate limited: 30/h) |
| GET | `/api/v1/theeemes/` | List all available theeemes |
| POST | `/api/v1/contact/` | Support/contact form (anonymous on purpose — a locked-out user is the main case; rate limited: 5/h per IP). Forwards the message to the operator with the sender as Reply-To; `kind: support\|collab` labels the subject (the `/contact` and `/collaborate` pages) |
| GET | `/api/v1/health/` | Health check: verifies app **and** database (`SELECT 1`) — 200 ok / 503 degraded. Point your uptime monitor here (rate limited: 60/min per IP, GET and HEAD — far above any real monitor's cadence) |
| - | `/oiueei-admin/` | Django Admin (requires password) |

**Note:** Reservation accept/reject actions can be performed via RSVP links sent by email or via authenticated API endpoints (`/bookings/{code}/accept/` and `/bookings/{code}/reject/`). Requesters can cancel their own pending bookings via `/bookings/{code}/cancel/`. Email links use RSVP codes as intermediaries to avoid exposing real codes in URLs.

## Deploying to Heroku

See [HEROKU.md](HEROKU.md) for a complete step-by-step guide covering buildpacks, config vars, font setup, and the deployment branch workflow.

## Running it for other people

This repository is the whole product, but not the layer an operator wraps around
it to run OIUEEI as a service: an open sign-up door, a queue of people asking to
be allowed to lend, a subscription. That is where an operator's judgement lives,
and it differs for every one of them.

So the mechanism is here and the policy is not. Four extension points let a
deployment add routes, decide who may create what, tell the frontend so it
stops offering what would be refused, and replace the SPA's pages and copy —
**without editing a file this repository also edits**, which is what makes an
upgrade a merge and not an argument. See [STANDALONE_HOSTED.md](STANDALONE_HOSTED.md).

## Development

```bash
# 1. Setup
python -m venv venv
source venv/bin/activate
pip install -r requirements/development.txt
cp .env.example .env  # Configure environment variables

# 2. Database (run before starting the servers)
python manage.py makemigrations core
python manage.py migrate

# 3. Seed demo data — recommended before exploring the app or running the frontend.
#    Without it the app is empty and there is no account to sign in as.
#    (Lala, Lele, Lili, Lolo, Lulu and their collections — idempotent.)
#    Collection/thing text is ALWAYS seeded in all three languages at once
#    (inline {es,ca,en} maps — every reader sees their own); --lang only picks
#    the language of the plain-column text (user bios, FAQs).
python manage.py seed_demo                 # plain-column text in English (default)
python manage.py seed_demo --lang=es       # … in Spanish (also: --lang=ca)
python manage.py seed_demo --lang=es --reset   # wipe demos first, then re-seed
# On Heroku (quote the inner command — the Heroku CLI otherwise grabs inner flags like --lang as its own):
#   heroku run --app <your-app> "python manage.py seed_demo --lang=es"
# Pass --reset to wipe existing demo data first (leaves other users/collections untouched).
# Adding a new language: copy core/management/commands/seed_data/en.py to e.g. pt.py,
# translate the text fields, add the code to SUPPORTED_LANGS in seed_demo.py.

# 4. Run the servers
python manage.py runserver                 # backend → http://localhost:8000
cd frontend && npm install && npm run dev  # frontend → http://localhost:3000 (separate terminal)

# 5. Tests & linting
pytest -v --cov=core --cov-fail-under=95   # backend tests (SQLite locally)
cd frontend && npm test                    # frontend tests (smoke + accessibility)
# CI runs this same backend suite against PostgreSQL — see Testing below.
ruff check .                               # lint + import sort (replaces flake8 + isort)
ruff format .                              # formatting (replaces black)

# Create admin user
python manage.py createsuperuser

# Scheduled jobs (run via Heroku Scheduler in production — one daily job chains them)
python manage.py expire_bookings   # expire stale bookings
python manage.py cleanup_rsvps     # delete expired RSVPs (24h+)
python manage.py close_transfers   # close overdue loan transfers
python manage.py send_reminders    # return reminders to BOTH sides of a loan (daily)
python manage.py send_digests      # weekly/monthly digest emails (daily)

# One-off: seed the Event analytics log from existing rows (idempotent).
# Run once, the day tracking ships, before forward events accumulate.
python manage.py backfill_events
```

## Testing

Backend `pytest` + `pytest-django`, frontend `vitest` + Testing Library + `jest-axe`.
Coverage floors are **ratchets, not targets** — they sit a couple of points under
the suite's real coverage so a regression is visible, and CI enforces both:
backend 95%, frontend 82/74/74/86 (statements/branches/functions/lines).

**CI runs the backend suite against PostgreSQL, not SQLite.** That is not parity
for its own sake. On SQLite, Django reports `has_select_for_update = False` and
*silently drops* the FOR UPDATE clause — no warning, the query just runs unlocked
— so every row-locked path (accepting, rejecting and cancelling a booking; the
capacity recheck on bulk import) would be proving its logic and never its lock.
That breaks with two concurrent requests, not two thousand. SQLite also doesn't
enforce `CharField(max_length=N)`, which PostgreSQL does.

A local `pytest` still runs on SQLite and needs no database server. To reproduce
a CI failure, point `DATABASE_URL` at a throwaway Postgres:

```bash
DATABASE_URL=postgres://user:pass@localhost:5432/oiueei_test pytest -q
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DJANGO_SECRET_KEY` | Yes | Django secret key |
| `JWT_SIGNING_KEY` | No | Signs JWTs independently of `DJANGO_SECRET_KEY`, so the two can be rotated separately (defaults to `DJANGO_SECRET_KEY` if unset). Setting/rotating it invalidates every issued access/refresh token — everyone re-logins via magic link — so change it deliberately, once, alongside a release. |
| `DJANGO_SETTINGS_MODULE` | No | Settings module (defaults to production) |
| `DJANGO_DEBUG` | No | Enables Django debug mode (default: `False` — fail-closed on a missing/typo'd value) |
| `DJANGO_ALLOWED_HOSTS` | No | Comma-separated allowed hosts |
| `DATABASE_URL` | Prod | PostgreSQL connection string. Also read by `development.py` — that is how CI runs the suite on Postgres (see Testing) |
| `DEV_DB_NAME` | No | Dev only: points the SQLite file elsewhere, so a migration can be rehearsed on a throwaway DB (`DEV_DB_NAME=/tmp/rehearsal.sqlite3 python manage.py migrate core 0121`). Ignored when `DATABASE_URL` is set |
| `MAGIC_LINK_BASE_URL` | Prod | Base URL for magic link emails (default in dev: `http://localhost:3000/verify`) |
| `CORS_ALLOWED_ORIGINS` | Prod | Comma-separated allowed origins |
| `CSRF_TRUSTED_ORIGINS` | Prod | Comma-separated trusted origins |
| `EMAIL_HOST` | Prod | SMTP host (default: smtp.sendgrid.net) |
| `EMAIL_PORT` | No | SMTP port (default: `587`) |
| `EMAIL_HOST_USER` | Prod | SMTP username |
| `EMAIL_HOST_PASSWORD` | Prod | SMTP password |
| `EMAIL_TIMEOUT` | No | SMTP socket timeout in seconds (default: `10`) — caps a slow/hung provider so it can't stall a web dyno |
| `EMAIL_LANGUAGE` | No | **Default** language for outbound email (`en`\|`es`\|`ca`; default `en`) — the weakest level of the hierarchy **deployment → collection (`Collection.language`) → recipient (`User.language`)**, so it only speaks when neither the group nor the member has chosen. Catalogues live in `core/services/email_texts/`; unknown codes fall back to English |
| `VITE_FEEDBACK_URL` | No | Frontend build-time: points the in-app feedback link at your own form (default: the project's Tally form) |
| `DEFAULT_FROM_EMAIL` | Prod | Sender email address |
| `RSVP_BASE_URL` | Prod | Base URL for RSVP action links in emails (default in dev: `http://localhost:3000/rsvp`) |
| `SHARE_LINK_BASE_URL` | Prod | Base URL for public collection share links (default in dev: `http://localhost:3000/share`) |
| `CLOUDINARY_URL` | Uploads | Cloudinary credentials for image uploads: `cloudinary://api_key:api_secret@cloud_name` (free account at cloudinary.com) |
| `CONTACT_EMAIL` | No | Recipient of the `/contact` support form (default: `DEFAULT_FROM_EMAIL` — the operator mails themselves) |
| `INVITE_EMAILS_PER_DAY` | No | Cap on invitation **emails** one account may send per day — single, bulk and approved member recommendations combined, whether the owner approves in the app or from the link in their email. **Unset or `0` = no limit**, which is the standalone default: this guards *your* sending domain's reputation, so the number is yours to choose (150/day is what www.oiueei.com uses). Ignored when `RATELIMIT_ENABLE` is off. |
| `COLLECTION_THINGS_ALARM` | No | Per-collection thing count that quietly emails the superusers **once**, so an operator can notice unusual volume without touching anything. **Unset or `0` = off** (the default). The owner is never told. |
| `COLLECTION_THINGS_BLOCK` | No | Per-collection ceiling on things: adds that would cross it are refused, including whole CSV batches. **Unset or `0` = off** (the default). A superuser lifts it per collection with `capacity_unblocked` in the admin. |
| `COLLECTION_INVITES_ALARM` | No | The same silent, fire-once alert for a collection's **member** count. **Unset or `0` = off**. |
| `COLLECTION_INVITES_BLOCK` | No | Per-collection ceiling on members: invitations that would cross it are refused when **sent**, not when accepted. **Unset or `0` = off**. Same `capacity_unblocked` override. |
| `TRUSTED_PROXY_COUNT` | No | How many proxies in front of the app are trusted to have appended to `X-Forwarded-For`. It decides which entry every per-IP rate limit buckets on, counted from the **right** — only the tail of that header is written by a proxy; the rest is the caller's own text. Default `1` = one trusted proxy (the Heroku/Render/Fly router, or an nginx you run). **Set `0` if nothing trusted sits in front** (gunicorn facing the internet): otherwise the header is caller-supplied and one caller can mint a fresh bucket per request, defeating every rate limit below. `2+` for a CDN in front of the router. |

## Onboarding & access

**There is no public self-registration.** An account exists because somebody chose to admit a specific person, and there are two ways that happens:

- **An owner invites you.** By email (the account is created when you accept), or through a public `/share/{token}` link — optionally as a QR — that the owner can rotate or revoke at any time. Either way you join **that one collection**.
- **You act on a PUBLIC collection.** Anyone can read a collection its owner made public; pressing an action button asks for your email, joins you to that collection and sends the magic link (`POST /auth/join/` with its code). It is login-to-act: reading needs nothing, acting needs an account.

`/login` (`POST /auth/request-link/`) is for people who already have an account. It always answers `200` — it never reveals whether an address is registered — and never creates users. `/auth/join/` likewise **creates nothing** unless the request carries a valid share token or public collection code, and answers identically whether or not it did.

**If your deployment wants an open door**, add one: a view of your own, mounted through `DEPLOYMENT_URLCONFS`, that creates the account and joins it to your `is_onboarding` collections. The mechanism is documented in [STANDALONE_HOSTED.md](STANDALONE_HOSTED.md); the policy is yours, which is why it is not shipped here.

## Security

### Implemented Measures

| Category | Measure | Description |
|----------|---------|-------------|
| Authentication | Magic Link | Passwordless auth via email (24h expiry, one-time use) |
| Authentication | JWT | HttpOnly cookie-based. 1-hour access, 7-day refresh with rotation and blacklist |
| Authentication | Invite-Only | New accounts come from an owner's invitation, an owner-enabled public share link/QR, or joining a PUBLIC collection to act on it. No endpoint creates an account that belongs to no collection. |
| Authentication | Admin 2FA | Django admin login requires a verified TOTP device (`django-otp` `OTPAdminSite`), on top of the password. Bootstrap the first device via `manage.py add_totp_device <email>`. |
| Authorization | DRF Permissions | Custom `IsThingOwner`, `IsCollectionOwner` permission classes |
| Authorization | IDOR Protection | Profile access only via collection connections |
| Input Validation | XSS Prevention | HTML escaped in emails via `django.utils.html.escape()`. Headlines sanitized |
| Input Validation | Image ID | Alphanumeric validation prevents path traversal |
| Rate Limiting | Auth | 5 req/min for magic link, 10 req/min for verify, 10 req/min for token refresh |
| Rate Limiting | Join (`/auth/join/`) | 5 req/min per IP + 5 req/hour per email |
| Rate Limiting | Collection invite | 30 req/hour per user |
| Rate Limiting | Collection bulk invite | 5 req/hour per user |
| Rate Limiting | Invitation emails | Off by default; set `INVITE_EMAILS_PER_DAY` to cap per account — single, bulk and approved recommendations combined, on both of the owner's routes |
| Rate Limiting | Collection share-link | 30 req/hour per user |
| Rate Limiting | Thing request | 10 req/hour per user |
| Rate Limiting | Thing bulk create | 10 req/hour per user |
| Rate Limiting | Thing report | 10 req/hour per user |
| Rate Limiting | Upload signature | 30 req/hour per user |
| Rate Limiting | Broadcast | 5 req/day per user |
| Rate Limiting | FAQ question | 20 req/hour per user |
| Rate Limiting | Notifications token | GET 20/min, PATCH 10/min per IP |
| Rate Limiting | Health check | 60/min per IP (GET + HEAD) — the one anonymous endpoint that reaches the database on every hit |
| Rate Limiting | Which IP a limit counts | The entry `TRUSTED_PROXY_COUNT` says a trusted proxy appended, counted from the right, **validated as an IP** before use; anything unparseable falls back to `REMOTE_ADDR` and then to one shared bucket — never to a fresh allowance |
| Rate Limiting | Thing single create | 60 req/hour per user |
| Rate Limiting | Collection single create | 30 req/hour per user |
| Rate Limiting | Collection add-thing | 60 req/hour per user |
| Rate Limiting | Collection leave | 30 req/hour per user |
| Rate Limiting | Collection digest pref | 30 req/hour per user |
| Rate Limiting | Recommend a guest | 30 req/day per member |
| Rate Limiting | Digest mute by token | 10 req/min per IP |
| Rate Limiting | Account delete request | 3 req/hour per user |
| Rate Limiting | Contact form | 5 req/hour per IP |
| Headers | HSTS | 1-year strict transport security with preload |
| Headers | X-Frame-Options | DENY (prevents clickjacking) |
| Headers | Content-Type | nosniff (prevents MIME confusion) |
| Headers | Referrer-Policy | strict-origin-when-cross-origin |
| Headers | Content-Security-Policy | Applied in every environment via `SecurityHeadersMiddleware` (`core/middleware.py`), plus a `Permissions-Policy` disabling camera/microphone/geolocation/payment. Violations are reported to **our own** `POST /api/v1/csp-report/` (`report-uri` + `report-to`) and logged to the `security` logger — a hosted collector would be handed the URL of every page a member visits, which §9 rules out |
| Production | SSL | Forced HTTPS redirect, secure cookies |
| Production | Admin Path | Custom path (`/oiueei-admin/`) instead of `/admin/` |
| Production | API Renderer | JSON-only in production (BrowsableAPI disabled) |
| Pagination | Max 100 | Prevents DoS via large page requests |

### Security Roadmap

- [ ] Email validation via AbstractAPI
- [ ] Audit logging to external service

## Privacy

Everything below is written so you don't have to take my word for it. Each claim comes with the way to check it yourself — "we take your privacy seriously" is what a page says when it has nothing checkable to offer.

### What the app does not do

- **No advertising.** No ad slots, no ad SDK, no ad network, no sponsored placement. Nothing in the product is sold to anyone who wants your attention.
- **No tracking, of any kind.** No analytics SDK, no tag manager, no fingerprinting, no session replay, no heatmaps, no A/B-testing service, no "anonymous" telemetry that phones home.
- **No third-party code running in your browser.** The app ships 12 runtime dependencies (React, HDS, i18next, a router, a QR renderer, a CSV/ZIP parser) — all rendering and parsing libraries, none of which talks to anyone. No script from another origin is loaded, ever.
- **No cookie banner, because there is nothing to consent to.** The only cookies are the technical ones that keep you signed in (auth + CSRF). There is no third-party cookie, no advertising cookie, no tracker to ask permission for — so asking would be theatre.
- **No tracking pixels or wrapped links in emails.** Links go where they say they go; there is no open-tracking pixel, no click-redirect domain.
- **No sale, sharing, profiling or automated decisions** on user data. [DESIGN.md §9](DESIGN.md#9-user-data-is-never-a-product) lists what is forbidden here under any justification — it is a design rule, not a policy page.

### How to check all of that

| Claim | How to verify it |
|---|---|
| Third-party scripts *cannot* load | `curl -sI https://www.oiueei.com/ \| grep -i content-security-policy` — the policy is `default-src 'self'; script-src 'self'`. A third-party script is blocked by the browser, not by a promise. See `core/middleware.py`. |
| Nothing is sent anywhere | DevTools → Network, on any page. You will see this origin and `res.cloudinary.com` (the photos). That is the whole list. |
| No trackers in the bundle | `frontend/package.json` — 12 runtime dependencies, all listed above. |
| Only technical cookies | DevTools → Application → Cookies. |
| The metrics are first-party | `core/models/event.py` and `core/models/activity.py` — an append-only event log and one `(user, date)` row. They record *less* than any web server log, and never leave the database. |
| All of it | The whole codebase is public. Read it. |

### What does leave the server

Four outbound flows exist, all operational, all named — the app is a normal web service, not a magic box:

1. **Hosting and database** — where the operator deploys it.
2. **Email delivery** — the configured SMTP provider (magic links, invitations, activity notices).
3. **Images and documents** — Cloudinary, which serves the photos to your browser and therefore sees the request.
4. **Error monitoring** — optional, deploy-only (Sentry). Events are scrubbed of cookies, auth headers, IP and user identity before being sent (`send_default_pii=False` + a `before_send` hook).

For the official deployment at **www.oiueei.com**, the verified locations are: application dyno in Heroku's **EU region**, PostgreSQL in **eu-west-1 (Ireland)**, email through **Mailgun's EU region** (`smtp.eu.mailgun.org`). Cloudinary and Sentry are, at the time of writing, on their US regions — which is why this README does not claim "everything is in Europe". The current state is always the one written on the [`/legal`](https://www.oiueei.com/legal) page.

### Your rights over your data

**Right to erasure is self-service, not a support ticket**: delete your own account from your profile (Edit profile → Delete account). Once confirmed via an emailed 24-hour link it is immediate and irreversible — the account, its collections, things, photos and pending requests are permanently deleted, Cloudinary assets included (`core/services/cloudinary_cleanup.py` runs on the delete). Questions you asked on other people's things and an item's transfer history survive **anonymised**: the content stays with the thing, your name goes ("former member").

For access, rectification, portability, objection or restriction, write to the operator — for www.oiueei.com, the address on the [`/legal`](https://www.oiueei.com/legal) page.


## Architecture Decisions

- **Service layer**: Business logic extracted into `core/services/` (email composition, booking accept/reject/cancel with `transaction.atomic()`). Views are thin controllers.
- **ModelViewSet + Router**: Collections and Things use DRF ModelViewSet with DefaultRouter for standard CRUD. Custom actions use `@action` decorator.
- **Proper FK/M2M**: All relationships use Django ForeignKey and ManyToManyField (migrated from JSONField arrays). This enables `select_related`/`prefetch_related`, cascade deletes, and referential integrity.
- **Centralized email**: All email HTML composition lives in `email_service.py` with `django.utils.html.escape()` for XSS prevention. Every send is routed through a preference pipeline that filters Cat. 2 (activity) and Cat. 3 (news) based on `User.notify_activity` / `notify_news`; Cat. 1 (magic links, invitations, revokes) is always delivered. Non-mandatory emails carry a footer with a `TimestampSigner`-signed link to `/me/notifications/{token}` so recipients can toggle preferences without logging in (see `NotificationsByTokenView`).
- **RSVP intermediary**: All email action links use RSVP codes. Real entity codes are never exposed in URLs.
- **Seed data out of migrations**: Demo fixtures (Lala/Lele/Lili/Lolo/Lulu and their collections) live in `core/management/commands/seed_demo.py` + `seed_data/{lang}.py`, not in migrations. Fresh environments start with a clean DB and only get demo data when `python manage.py seed_demo` is run explicitly. The command is idempotent (`update_or_create` / `get_or_create`). Collection/thing text is always seeded **in all three languages at once** as inline localized maps (`{"es": …, "ca": …, "en": …}` — every reader resolves their own, see the multilingual-content notes); `--lang=en|es|ca` (default English) only selects the language of the plain-column text (user bios, FAQs). The old seed migrations (`0037`–`0076`) are retained as no-ops to preserve migration history.

## Default Data

- Default Theeemes (system baseline, seeded by migration `0036`): the 12 canonical palettes (Bussi, Engel, Hopea, Kesä, Kupari, Kulta, Metro, Sumu, Spåra, Suomenlinna, Vaakuna, M&V).
- Demo users/collections/things: **not** created automatically — run `python manage.py seed_demo` to populate.

## Important Notes

- **Superadmin must be created manually** after running migrations:
  ```bash
  python manage.py createsuperuser
  ```
  This is required to access `/oiueei-admin/`. Regular users authenticate via magic link and don't need passwords.

- **Admin login also requires 2FA**: `/oiueei-admin/` is an `OTPAdminSite` (`django-otp`) — password auth alone isn't enough. Bootstrap the first TOTP device (no admin login needed) with:
  ```bash
  python manage.py add_totp_device <email>
  ```
  Scan the printed `otpauth://` URI into an authenticator app. Additional staff can then have devices added via the admin's own TOTP device page once one verified login exists.

- **Booking expiration** - PENDING bookings expire after 72 hours. Run `python manage.py expire_bookings` periodically (Heroku Scheduler recommended).

## Accessibility

OIUEEI targets [WCAG 2.1 AA](https://www.w3.org/TR/WCAG21/) as a minimum across all views. This commitment is structural, not aspirational — accessibility decisions are embedded in the design system, the theeeme colour palettes, and the component library.

### Theeeme Colour Contrast

Every theeeme palette has been verified for WCAG contrast compliance across all six colour roles (koros section, primary and secondary buttons, body text). The table below summarises the results:

| Compliance | Theeemes |
|------------|----------|
| AAA for all colour roles | Bussi, Kupari, Engel, Hopea, Suomenlinna, M&V, Vaakuna |
| AAA for all roles except AA for normal text in koros section | Metro, Spåra |
| AAA for all roles except AA for normal text in primary button | Kesä, Sumu |
| AAA for all roles except AA for normal text in koros section and primary button | Kulta |

All theeemes meet AA or higher for every colour combination. No theeeme falls below AA for any role.

### HDS Accessibility Foundation

All UI components are sourced from the [Helsinki Design System](https://hds.hel.fi/), which is WCAG 2.1 AA audited. HDS provides accessible form controls (labels, error states, focus indicators), keyboard navigation, and screen reader support out of the box. Custom components follow HDS visual conventions and accessibility patterns.

### Implemented Measures

- **Semantic HTML** — proper heading hierarchy (`h1` for page titles, `h2` for sections), form elements with associated labels via HDS components
- **Decorative icons** — all HDS icons in info rows use `aria-hidden="true"` to avoid screen reader noise
- **Live regions** — toast notifications use `aria-live="polite"` for non-intrusive screen reader announcements
- **Accessible tooltips** — `TooltipButton` provides `aria-label` for icon-only actions
- **Image alt text** — thing thumbnails and gallery images include meaningful `alt` attributes derived from headlines
- **Page titles** — every page sets `document.title` via `useEffect` for meaningful browser tab titles and screen reader orientation
- **Language attribute** — `<html lang>` is set dynamically on the document root via `i18n.on('languageChanged', ...)` in `App.jsx`
- **Internationalisation** — all UI strings are externalised via `react-i18next` with automatic browser language detection (`i18next-browser-languagedetector`). Supported: English, Spanish, Catalan. Brazilian Portuguese, European Portuguese, Basque, and Galician are paused (not deleted) and fall back to Spanish

### Validation

Main pages are validated with [axe DevTools](https://www.deque.com/axe/devtools/) to detect WCAG violations. Automated accessibility checks are integrated into the frontend test suite via `jest-axe`.

## Legal

The app ships a public **`/legal`** page (commitment, legal notice, privacy, basic terms — es/ca/en, following the UI language). Its content lives in `frontend/src/legal/{lang}.js` and is **per-deployment**:

- The standalone repo carries a **generic, operator-neutral** text. **If you self-host OIUEEI, you are the data controller of your instance**: edit those files with your identity, contact, legal bases and processors before inviting real users.
- The official deployment (www.oiueei.com) replaces those files on its deploy branch with the full RGPD/LSSI version of its owner.

**Licence**: [Business Source License 1.1](LICENSE) — the code is public and auditable, production self-hosting is allowed, and the one restriction is offering OIUEEI to third parties as a hosted service that competes with the licensor's paid offering. On the Change Date (2030-02-02) it becomes MIT.

### Need a hand running your own OIUEEI?

Self-hosting is allowed and encouraged. If you'd like help deploying your own instance, adapting it to your community, or building custom features on top of it, I offer exactly that as an on-demand service — write to **oiueei@disroot.org** and tell me what you have in mind.

## Acknowledgements

This project uses components and design tokens from the [Helsinki Design System](https://hds.hel.fi/) by the [City of Helsinki](https://github.com/City-of-Helsinki), licensed under the [MIT License](https://github.com/City-of-Helsinki/helsinki-design-system/blob/master/LICENSE).

Instead of [Helsinki Grotesk](https://hds.hel.fi/foundation/design-tokens/typography/) by [Camelot Typefaces](https://camelot-typefaces.com) (the default shipped with HDS), we are using [Curiosa](https://fabiohaagtype.com/en/font/curiosa/) by [Fabio Haag Type](https://fabiohaagtype.com/en/) as the display typeface; a warm hug to the Haag team for their kindness.

QR codes for collection share links are rendered client-side with [qrcode.react](https://github.com/zpao/qrcode.react) by Paul O'Shannessy, licensed under the [MIT License](https://github.com/zpao/qrcode.react/blob/main/LICENSE).

CSV files for bulk-adding things are parsed client-side with [PapaParse](https://github.com/mholt/PapaParse) by Matt Holt, licensed under the [MIT License](https://github.com/mholt/PapaParse/blob/master/LICENSE).

The backend test suite builds model fixtures with [factory_boy](https://github.com/FactoryBoy/factory_boy) and freezes time deterministically with [time-machine](https://github.com/adamchainz/time-machine) by Adam Johnson, both licensed under the [MIT License](https://github.com/FactoryBoy/factory_boy/blob/master/LICENSE) (development-only dependencies).

This project is co-written with [Claude Code](https://claude.ai/code) by [Anthropic](https://www.anthropic.com/).

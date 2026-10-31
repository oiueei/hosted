# `hosted/` — the service layer of this deployment

Everything in here is this operator's own service layer — the open door, the
vetting policy, whatever any of it costs. It is not the OIUEEI product (that is
`oiueei/standalone`); it is what *this* deployment adds on top, kept in this repo
under the same EUPL-1.2 licence because a modified copy run as a network service
owes its source to the people who use it. **This app only ever adds.** It mounts
its own URLs, supplies its own policy, brings its own migrations, and imports
from `core` while `core` knows nothing about it — so a merge from upstream stays
a merge.

If you are looking for what upstream offers a deployment, that is
[SELF_HOSTING.md](../SELF_HOSTING.md). This is what *this* deployment
did with it.

## Where a fix belongs

Not every fix that surfaces while working on this deployment belongs in this
repository. Before committing, ask where the changed files actually live — not
where the bug was *found*:

- **Product bug** — the changed files are under `core/`, or under `frontend/`
  outside this deployment's own directories — belongs in `oiueei/standalone`,
  even when a hosted-specific scenario (COMMUNITY mode, `HostedCreatorPolicy`
  narrowing a policy) is what surfaced it. Fix it upstream first: commit
  against `development`, merge into `main`, push both — *then* merge that
  `main` into this repo's `main` to bring the fix here. This repo tracks
  upstream with exactly that merge, so a fix that lands only here is invisible
  to it and has to be re-applied by hand on every future sync, forever.
- **Deployment bug** — the changed files are this deployment's own: `hosted/`,
  `frontend/src/deployment/` (all of it except `index.js`, which is upstream's
  contract and the one file there that both sides edit),
  `frontend/src/legal/{ca,en,es}.js`, and the settings that mount them — fix it
  here, same as any other commit.

The tell is the file path, not where the session happened to be checked out.
That last part earns a second of care when the two repos are two branches of
one working copy rather than two clones: nothing about the files on disk says
which `main` they are heading for, so confirm the branch before committing a
`core/` change.

Publishing this code makes the **mechanism** transparent — the request form, the
`CreatorValidation` model, the admin action, the policy class. It does not make
the **criterion** transparent: which answer to "what are you planning to run
here?" earns a yes is a case-by-case judgement that lives in no file, the same
honesty note `SELF_HOSTING.md` makes about the extension points.

## What it does

| Piece | What it is |
|---|---|
| `views.PopInView` | The **open door**: an email alone gets an account, membership of every `is_onboarding` collection, and a magic link. Served at the historical `/api/v1/auth/pop-in/`. Upstream refuses exactly this. |
| `tally.py` | Where **"Request access"** and **"Contact us"** live: for each, three forms on Tally, one per language (`es`, `ca`, `en`), opened in a new tab. "Request access" used to be a Django page of our own at `/request-access/` with two free-text questions; the request now lands in Tally and the answer is still given here, in the admin. The server needs the addresses in three places the SPA does not render — `capabilities.request_url`, the two 403 bodies that say where to ask, and the email of a refusal — and `request_access_url(language)` gives the one of the account's language (`es` when blank). The SPA has its own copy (`externalForms.requestAccess`), and a test reads both files so they cannot come apart. The old address of the page, `/request-access/` (and without the slash), is still in the emails of refusals sent before the move and in bookmarks: `views.RequestAccessRedirect` sends it, with a 302, to the form of the `?lang=` of the link when it is one of `REQUEST_ACCESS` (the app's `/access` page adds the language on screen to its buttons: `?for=<need>&lang=<es|ca|en>`) and otherwise of the browser's `Accept-Language` (`browser_language`: the first language asked for that has a form, else `es`). Nothing is added to the address of the form and the `ASKED` count is the same. `/contact`, core's own page, is typed and bookmarked too and goes the same way: `views.ContactRedirect` sends it, with a 302, to the "Contact us" form of the browser's language (`contact_url`); a link inside the app never asks the server, which is why the footer points at Tally itself. The same test reads the SPA's `contact` addresses against `CONTACT`. |
| `models.CreatorValidation` | One row per person who asked, and the answer (the request itself is in Tally). **No column on `core.User`**, so the public schema says nothing about a gate it does not have. |
| `policy.HostedCreatorPolicy` | The **narrowing**: giving and selling are open to everyone; COMMUNITY and NETWORK collections, lending, renting and on-site reservations wait for approval (the approved account gets every mode, so a network included). |
| `admin.py` | Where you answer, behind the admin's existing OTP. A request arrives through Tally, so the row is made by hand: **Add**, find the account by its email (autocomplete), copy the two answers from Tally into **Who** and **Intent**, pick the status and a note. The answers keep why each decision was taken in the database and not only in Tally; left empty they say `(enviado por Tally)`, and they can be corrected afterwards (the admin's History keeps each change, and changing them mails nobody). Choosing a status on the form is a decision like the **Approve** / **Reject** actions: it stamps when and mails the answer (a note on its own, or a status left as it was, mails nobody). No migration: the two columns stay required, and only the **Add** form lets them be left empty. |
| `management/commands/stats_summary.py` | The weekly **operator report**, with its demo/real partition and, since the series exists, three sections read from it: the last twelve weeks, the organic cycle from guest to owner, and the average week of each phase. |
| `viral.py` | **The growth line at the foot of an email, chosen per recipient.** Core ends every email with one line inviting its reader to start something of their own; here some of that has to be asked for first, so `pick_line(user, lang)` — the function `VIRAL_LINE_PROVIDER` points at — picks one of fifteen lines (three languages) and sends the recipient where they can act: the form of the kind when this deployment lets them (`/stall/new`, `/library/new`, `/shed/new`, `/new` for the generic one), otherwise `/access/library` or `/access/shed`. A stall is open to everyone, community or not, and one permission covers a whole library (lending and renting out), so the kind is all that is asked. The plug is a Heroku config var the operator sets: `heroku config:set VIRAL_LINE_PROVIDER=hosted.viral.pick_line --app <app>`; without it the emails keep core's lines. It asks the creator policy once per line; an address with no account is treated as one that has not asked. |
| `models.AccessInterest` | **Numbers only** behind the request-access page: per day and need (`library`, `shed`), how many times a section was opened (`SEEN`, from `POST /api/v1/access/seen/`, public, no authentication, 30 a minute per address) and how many times its "Request access" button was pressed (`ASKED`, a `?for=<need>` on `/request-access/`, which still redirects to the form exactly as before). No user, address or User-Agent in a row, so no retention period; the admin is read-only. Rows of the two sections the page used to have (`rent`, `community`) stay in the table, uncounted and unlisted. The Monday summary reads it in "Interest in what opens on request (last week)", next to "Devices (last week)" (core's `DeviceDay`, through `device_share`'s function). |
| `metrics.py` | **One week of the series**, derived from the `Event` log: stocks at the cutoff, movements of the week and the cycle, as pure functions. The backfill and the live recording call the same one, so they cannot disagree. |
| `models.WeeklySnapshot`, `models.Milestone` | The stored series (one row per closed week, **aggregates only**) and the days each phase began, edited in the admin. The snapshots are read-only there. |
| `management/commands/record_weekly_snapshot.py` | Stores the last closed week (idempotent, so it runs daily); `--backfill-from` rebuilds the past from the log. |
| `management/commands/stats_history.py` | Prints the series as CSV for a spreadsheet (`--cohorts` for the conversion triangle). |
| `../frontend/src/deployment/` | The SPA half: the `/popin`, `/welcome` and `/access/:need` pages (the last explains what opens on request, in two sections — a library of things and a shed — each with its own button to the form), `requestAccessPaths` (`{ LIBRARY: '/access/library', SHED: '/access/shed' }`: on `/new` the "Request access" of a library's or a shed's card goes to that page in the same tab, and a community is asked for from the collection form's own option, which opens the Tally form), their copy in three languages, and the values (`popInPath`, `aboutPath`, `faqPath`, `externalForms`) that make the shared components behave like a hosted service. `externalForms` is the nine Tally forms (the footer's "Contact us", "Ideas and bugs" and "Request access", each in `es`, `ca` and `en`, opened as written in a new tab): the shared components prefer them to `/contact`, `VITE_FEEDBACK_URL` and the server's request address, so the Heroku variable `VITE_FEEDBACK_URL` is no longer needed. `popInPath` is `/welcome`, not `/popin`: the "new here?" button on `/login` takes a stranger to the page that says what this is, whose last row of buttons (after the personas; a stranger's hero has none) offers the open door (`/popin`), the FAQ and the way back to `/login`. |

## What it needs

Set in `config/settings/production.py`, not left to config vars — an app whose
routes are not mounted fails **silently**:

```python
INSTALLED_APPS += ["hosted"]
DEPLOYMENT_URLCONFS = [*DEPLOYMENT_URLCONFS, "hosted.urls"]
CREATOR_POLICY = "hosted.policy.HostedCreatorPolicy"
```

Config vars, both optional:

| Var | Effect |
|---|---|
| `STATS_EMAIL` | Where the weekly report goes. Unset ⇒ the command prints and skips the email. |
| `STATS_EMAIL_WEEKDAY` | Which day it sends (0=Monday … 6=Sunday, default Monday). |
| `STATS_WEEK_TZ` | The time zone in which a week of the series runs from Monday 00:00 to Sunday 23:59 (default `Europe/Madrid`), whatever `TIME_ZONE` is. |

**The scheduler is not in this repository.** Heroku Scheduler lives in the
dashboard and nowhere else, so this section is the only readable copy of what
that job says. One daily job, every command guarded so that one failure neither
cancels the rest nor goes unseen:

```
rc=0; python manage.py expire_bookings || rc=1; \
python manage.py cleanup_rsvps || rc=1; \
python manage.py close_transfers || rc=1; \
python manage.py send_reminders || rc=1; \
python manage.py send_digests || rc=1; \
python manage.py record_weekly_snapshot || rc=1; \
python manage.py stats_summary || rc=1; \
python manage.py purge_expired_data --commit || rc=1; \
exit $rc
```

Every command runs even if the one before it failed, and the job ends red if any
of them did (`exit $rc`): chained with `&&`, a failure in the first stage left that
day without the email and without the purge. It is the same shape that `HEROKU.md`
teaches for the upstream commands, with its reasons: see "Scheduled jobs (cron)"
there. (Paste it on one line in the dashboard; the backslashes are only for
reading.)

A **second job**, `python manage.py cleanup_orphan_images --bucket <bucket> --commit`,
runs daily at 05:30 UTC, a little after the chain. It is upstream's too, and it is
not chained on purpose (see the end of that same section of `HEROKU.md`).

`record_weekly_snapshot` goes **right before** `stats_summary`: on Monday the week
that has just closed is then already stored when the email is built.

**Six of the eight are upstream's** — `HEROKU.md` explains each, including
`purge_expired_data`, which lives in `core/` and became the sixth link of that
guide's own chain on 2026-08-24. Two commands here are this deployment's:

| Command | Whose | What it does here |
|---|---|---|
| `record_weekly_snapshot` | **This deployment** | Stores the last closed week of the series if it is missing, and says so when there is nothing to do. |
| `stats_summary` | **This deployment** | The weekly operator report. No-ops on the other six days. |
| `purge_expired_data` | Upstream (`core/`) | Enforces the retention periods (GDPR art. 5.1.e). What belongs to this deployment is not the command — it is the decision to run it with `--commit`, and the `RETENTION_*` periods it obeys. |

**`purge_expired_data` runs with `--commit`, and it was armed on purpose rather
than by default.** It was first run by hand against production on 2026-08-23
(`heroku run -a <app> "python manage.py purge_expired_data"`, which is a dry run
— the flag is what makes it act) and every one of its eight categories came back
zero. That is the expected answer and not a lucky one: this deployment was three
weeks old in February 2026, so seven of the eight measure periods (12, 14, 24 and
26 months) that no data here can possibly have reached yet. The only line that
could have been non-zero is the 60-day one, guests who never came in, and it was
zero too.

So there is no backlog: whatever crosses a period first will be one row, not a
pile. The nearest one is notifications and reports at 12 months — around February
2027 — and the irreversible step, deleting an inactive account, cannot happen
before 24 months of inactivity **plus** the 30 days its warning email announces.
Waiting for a non-zero before arming it would have meant leaving a job that
prints zeros for half a year and remembering to come back to it, which is the
kind of thing nobody does.

To preview it at any time without touching anything, run it without the flag:

```bash
heroku run -a <app> "python manage.py purge_expired_data"
```

The periods in force are the settings' defaults; every one is a `RETENTION_*`
config var if this deployment ever wants a different number, and **0 means keep
indefinitely**:

| Data | Period |
|---|---|
| Inactive accounts | 24 months, warned by email 30 days first |
| Invited guests who never came in | 60 days |
| Analytics log (`Event`) | **anonymised**, not deleted, at 14 months |
| Weekly snapshots | aggregates only, no personal data — kept indefinitely: they are what survives when the `Event` log loses the link to people at 14 months |
| Daily activity rows | 26 months |
| In-app notifications | 12 months |
| Reports | 12 months |

Check what is actually set with `heroku config -a <app> | grep RETENTION`; no
output means all of the above are the defaults, which is the intended state.

One exception worth knowing before reading the output: **an account that owns a
collection with members is never deleted automatically**, however inactive.
Cascading it would take the group's library with it, so the command prints the
code and leaves the decision to a person.

## The weekly series

The email of one Monday is a photograph and is gone by the next; the series is what is
kept. Each closed week is stored as a `WeeklySnapshot` of counts and medians (never a
user code), so it can be kept for ever, and the cohort triangle in the last snapshot
survives the anonymisation of the `Event` log.

**How to read it**

- **A week** runs Monday 00:00 to Sunday 23:59 in `STATS_WEEK_TZ`. Week 0 is the one of
  7 September 2026.
- **Real** is decided event by event: the five seed characters, onboarding collections,
  joins through the open door and things added in onboarding are out. The accounts of the
  operator count. Somebody who has since left their group still counts in the weeks they
  were in it.
- **The characters stand for nothing, whoever acts.** To try something in production
  without touching the numbers, sign in as one of the five characters: nothing they do,
  and nothing done in their collections or on their things, reaches the statistics. The
  person who asked or joined is not erased; only that event stops counting, so their first
  real entry may become the next one.
- **What vanished without a trace is left out.** Deletions are logged by the models, so
  from now on nothing disappears silently; for what was lost before, four rules read what
  exists today and apply only to what left no event: a collection that was created, never
  deleted and no longer exists never happened (nor did what was in it); a thing in a
  collection that was deleted, with no removal and no longer existing, counts as removed
  when its collection went (not as a movement of that week); a thing with no trace in a
  collection that still exists never happened; and somebody who no longer has an account
  leaves their groups at their last event, staying in the history for the weeks they were
  there.
- **A new person** is somebody whose first real event is a join or a collection created.
  A visit through `/popin` is not one.
- **Stocks** (creators, guests, collections, memberships, things) are rebuilt from the log
  at each week's end: a collection lives until its deletion, a membership until the
  member's last leave, a thing until its removal.
- **The cycle** follows people who entered as guests through six stages: came in, came
  back (a second day active), asked for something, became an owner, added a first thing,
  brought somebody in. The stages count how many people reached each, in no required
  order between the second and the third.
- **Generations:** an owner who had no join before their first collection is *seeded*
  (generation 0); an organic owner is one more than the owner of the collection of their
  first join. **K** for a generation is owners of the next over owners of this one, shown
  as `a/b = x.xx` with its two factors: guests brought per owner, and the share of them
  who became owners.
- **Small samples:** always `n/N`, with a percentage only from N = 10. Times are medians.
- Weeks recorded as `BACKFILL` have no value for `collections_community`,
  `collections_network`, `collections_public` and `things_available`: they describe the
  state of the day and the log cannot say what it was. (`collections_network` is later than
  the first weeks, so those rows have no such key at all; the history file leaves the cell
  empty, as for any other gap.) The Monday report counts a network on a row of its own
  (`NETWORK`) and keeps `COMMUNITY / PROPRIETARY` for those two modes alone: a network is
  neither, and counted as proprietary it would hide the mode this deployment asks approval for.

**Starting it**

1. In the admin, add the milestones: "Early adopters" on 2026-09-07 (`EARLY_ADOPTERS`), and
   each launch on the day it happens.
2. Rebuild the past once:
   `heroku run --app <app> "python manage.py record_weekly_snapshot --backfill-from 2026-09-07"`.
3. Put `record_weekly_snapshot` before `stats_summary` in the scheduler job (above).
4. Whenever you want the table:
   `heroku run --no-tty --app <app> "python manage.py stats_history" > serie.csv`.

`--rebuild` recomputes weeks that exist and refuses to go back past the 14 months after
which the log has lost who did what.

## Running the door

```bash
python manage.py migrate                 # creates hosted_creator_validations
python manage.py seed_demo               # the collections /popin joins people to
```

Without `is_onboarding` collections the door still works — the account is real
and the magic link arrives — there is simply nothing to put anyone in.

## Tests

They live in `core/tests/` (`test_hosted_*.py`, plus
`scenarios/test_hosted_tracking_flow.py`) and the frontend's in
`frontend/src/deployment/`. That is not where they belong conceptually; it is
where they **run**. `pytest.ini` sets `testpaths = core/tests` and is merged
unchanged from upstream, so a suite anywhere else is silently never executed —
which has already happened once, to another app. Adding a file there conflicts
with nothing; editing `pytest.ini` here would conflict on every sync.

CI runs them twice, for two different reasons. The shared workflow
(`pytest --cov=core --cov-fail-under=96`) runs them on PostgreSQL and gates
their **correctness**, like every other test — but its 96% measures `core`
only. So a second workflow, which exists only in this repo, gives this app its
own **floor**:

```bash
# .github/workflows/hosted.yml, and what to run before you push
pytest core/tests -k hosted --cov=hosted --cov-fail-under=97
```

Two seconds, 88 tests, and the app sits at 99%.

The floor is not a `--cov=hosted` added to the shared workflow, for two
reasons worth knowing before somebody "simplifies" this. That file is merged
unchanged from upstream by design, so an edit made *here* would conflict on
every future sync. And a combined total would not be a floor anyway: `hosted/`
is 351 statements inside a 5,126-statement suite, so under a 96% combined gate
it could quietly rot to about 59% before any build noticed.

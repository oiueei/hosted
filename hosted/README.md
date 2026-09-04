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

Publishing this code makes the **mechanism** transparent — the form, the
`CreatorValidation` model, the admin action, the policy class. It does not make
the **criterion** transparent: which answer to "what are you planning to run
here?" earns a yes is a case-by-case judgement that lives in no file, the same
honesty note `SELF_HOSTING.md` makes about the extension points.

## What it does

| Piece | What it is |
|---|---|
| `views.PopInView` | The **open door**: an email alone gets an account, membership of every `is_onboarding` collection, and a magic link. Served at the historical `/api/v1/auth/pop-in/`. Upstream refuses exactly this. |
| `views.RequestAccessView` + `forms.py` | The **request form** at `/request-access/` — two free-text questions, a plain Django page outside the SPA. |
| `models.CreatorValidation` | One row per person who asked, and the answer. **No column on `core.User`**, so the public schema says nothing about a gate it does not have. |
| `policy.HostedCreatorPolicy` | The **narrowing**: giving and selling are open to everyone; COMMUNITY collections, lending and renting wait for approval. |
| `admin.py` | Where you answer, behind the admin's existing OTP. |
| `management/commands/stats_summary.py` | The weekly **operator report**, with its demo/real partition. |
| `../frontend/src/deployment/` | The SPA half: the `/popin` and `/welcome` pages, their copy in three languages, and the two paths (`popInPath`, `aboutPath`) that make the shared components behave like a hosted service. |

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

**The scheduler is not in this repository.** Heroku Scheduler lives in the
dashboard and nowhere else, so this section is the only readable copy of what
that job says. One daily job, everything chained with `&&` so a failure stops
the chain and shows up in scheduler-monitor:

```
python manage.py expire_bookings && python manage.py cleanup_rsvps && \
python manage.py close_transfers && python manage.py send_reminders && \
python manage.py send_digests && python manage.py stats_summary && \
python manage.py purge_expired_data --commit
```

**Six of the seven are upstream's** — `HEROKU.md` explains each, including
`purge_expired_data`, which lives in `core/` and became the sixth link of that
guide's own chain on 2026-08-24. Only one command here is this deployment's:

| Command | Whose | What it does here |
|---|---|---|
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
| Daily activity rows | 26 months |
| In-app notifications | 12 months |
| Reports | 12 months |

Check what is actually set with `heroku config -a <app> | grep RETENTION`; no
output means all of the above are the defaults, which is the intended state.

One exception worth knowing before reading the output: **an account that owns a
collection with members is never deleted automatically**, however inactive.
Cascading it would take the group's library with it, so the command prints the
code and leaves the decision to a person.

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

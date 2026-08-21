"""
Enforce the retention periods (GDPR art. 5.1.e).

"How long do you keep this?" used to have one honest answer here — "forever" —
and that is not a valid one. This command is the other half of a decision taken
on paper first: a period per category of data, with a reason. It does not
invent any of them; every period is a setting (``RETENTION_*`` in
``config/settings/base.py``), and **0 means keep indefinitely** for a deployment
under a different regime.

**Dry-run is the default**, like ``cleanup_orphan_images``: this deletes real
rows, so it is meant to be looked at before it is trusted. Pass ``--commit``.

    python manage.py purge_expired_data            # count what would go
    python manage.py purge_expired_data --commit   # actually do it

Idempotent: every step selects only rows that are still in the "before" state,
so running it twice in a row does nothing the second time, and a run that dies
half way can simply be run again.

Two shapes of expiry, and the difference is the whole point:

- **Anonymised** — ``Event``. What expires is the link to a person
  (``actor_code``), not the fact that something happened. The series survives as
  aggregate and stops being personal data, which is what art. 5.1.e asks for;
  deleting it would throw away the history to achieve the same thing.
- **Deleted** — the guest accounts nobody ever answered for, ``DailyActivity``,
  ``InAppNotification``, ``Report``. There is no version of these that stops
  being about somebody.
"""

import calendar
import logging
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import RSVP, DailyActivity, Event, InAppNotification, Report, User

security_logger = logging.getLogger("security")


def months_ago(months, now=None):
    """The same day of the month, ``months`` calendar months back.

    Calendar arithmetic rather than ``timedelta(days=30 * months)`` because a
    retention period is stated in months and a person whose data is deleted six
    days early has a point. The day is clamped to the length of the target month
    (31 March → 28 February).
    """
    now = now or timezone.now()
    year = now.year + (now.month - 1 - months) // 12
    month = (now.month - 1 - months) % 12 + 1
    return now.replace(
        year=year, month=month, day=min(now.day, calendar.monthrange(year, month)[1])
    )


class Command(BaseCommand):
    help = "Anonymise or delete data past the retention period set for its category."

    def add_arguments(self, parser):
        parser.add_argument(
            "--commit",
            action="store_true",
            help="Actually apply it. Without this flag the command is a dry-run (default).",
        )

    def handle(self, *args, **options):
        commit = options["commit"]
        now = timezone.now()
        steps = [
            self._unvisited_guests,
            self._events,
            self._daily_activity,
            self._notifications,
            self._reports,
        ]
        results = [result for result in (step(now, commit) for step in steps) if result]

        self.stdout.write("Retention sweep — " + ("COMMITTED" if commit else "DRY RUN"))
        for label, count in results:
            self.stdout.write(f"  {label}: {count}")
        total = sum(count for _, count in results)
        if not total:
            self.stdout.write(self.style.SUCCESS("Nothing past its retention period."))
            return
        if commit:
            # An automated erasure leaves the same trail a user-requested one does.
            security_logger.info(
                "Retention sweep applied: "
                + ", ".join(f"{label}={count}" for label, count in results)
            )
            self.stdout.write(self.style.SUCCESS(f"Applied to {total} rows."))
        else:
            self.stdout.write(
                self.style.WARNING(f"{total} rows are past their period. Re-run with --commit.")
            )

    def _unvisited_guests(self, now, commit):
        """Accounts created by somebody else's invitation that were never used.

        ``User.objects.get_or_create(email=...)`` writes a row the moment an
        owner types an address, so an invitation nobody answers leaves a
        stranger's email in the database indefinitely. That address came from a
        third party (art. 14) and was used for exactly one thing: sending an
        invitation that went unanswered.

        Each condition is a distinct way of being wrong about somebody, which is
        why each has its own negative test:

        - ``last_activity`` is null — they never came in. Accepting an
          invitation means signing in, which writes it.
        - in no collection's ``invites`` — the membership M2M is written on
          **accept**, not on invite, so a row here is somebody who did answer
          and simply hasn't been back. Sweeping them would remove a real member
          from a real group.
        - owns no collection and no thing — content means a person, whatever the
          activity column says.
        - has no live ``COLLECTION_INVITE`` RSVP — their invitation is still
          open and may yet be accepted. **Not** "an expired RSVP": ``cleanup_rsvps``
          runs daily and deletes those, so by the time this looks there is no
          expired row to find. Absence is what expiry looks like from here, and
          ``User.created`` is what dates it.
        - not staff or superuser — an admin account created with
          ``createsuperuser`` and never used through the SPA matches every
          condition above.
        """
        days = settings.RETENTION_UNVISITED_GUEST_DAYS
        if not days:
            return None
        codes = list(
            User.objects.filter(
                last_activity__isnull=True,
                created__lt=(now - timedelta(days=days)).date(),
                is_staff=False,
                is_superuser=False,
                invited_to_collections__isnull=True,
                owned_collections__isnull=True,
                owned_things__isnull=True,
            )
            .exclude(rsvps__action=RSVP.Action.COLLECTION_INVITE)
            .values_list("code", flat=True)
        )
        if commit and codes:
            # Erased in bulk, counted in the log and not named there: once the
            # row is gone, writing the codes into a file that outlives it would
            # be an odd way to honour a retention period.
            User.objects.filter(code__in=codes).delete()
        return (f"Guest accounts never used, deleted (>{days}d)", len(codes))

    def _events(self, now, commit):
        """Cut the link to a person; keep the fact.

        Excluding rows already anonymised is what makes this idempotent — and
        what stops a second run from reporting the same thousands of rows again.
        """
        months = settings.RETENTION_EVENT_ANONYMISE_MONTHS
        if not months:
            return None
        rows = Event.objects.filter(created__lt=months_ago(months, now)).exclude(actor_code="")
        count = rows.count()
        if commit and count:
            rows.update(actor_code="")
        return (f"Event rows anonymised (>{months}m)", count)

    def _daily_activity(self, now, commit):
        months = settings.RETENTION_DAILY_ACTIVITY_MONTHS
        if not months:
            return None
        rows = DailyActivity.objects.filter(date__lt=months_ago(months, now).date())
        count = rows.count()
        if commit and count:
            rows.delete()
        return (f"Daily activity rows deleted (>{months}m)", count)

    def _notifications(self, now, commit):
        months = settings.RETENTION_NOTIFICATION_MONTHS
        if not months:
            return None
        rows = InAppNotification.objects.filter(created__lt=months_ago(months, now))
        count = rows.count()
        if commit and count:
            rows.delete()
        return (f"Notifications deleted (>{months}m)", count)

    def _reports(self, now, commit):
        """Dated from ``created``: the model has no "resolved" state to date from,
        and adding one would be a moderation feature, not a retention decision."""
        months = settings.RETENTION_REPORT_MONTHS
        if not months:
            return None
        rows = Report.objects.filter(created__lt=months_ago(months, now))
        count = rows.count()
        if commit and count:
            rows.delete()
        return (f"Reports deleted (>{months}m)", count)

"""
Management command to tell each group's curators who joined since the last summary.

One email per curator (the founder and the co-curators) for every ACTIVE
collection that had sign-ups, read from the ``Event`` log. Run once a day, before
``send_digests``, from the Heroku Scheduler.

A collection's last summarised day lives in ``Collection.join_summary_sent_on``
and is claimed with a conditional UPDATE **before** anything is sent, so a second
run the same day (or two at once) finds nothing to do. The window runs from the
day after that one to yesterday, never more than ``MAX_DAYS`` back, so a day the
Scheduler skipped loses no sign-ups. Only people still in the group are named; a
person who joined and left in the window is not.
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from core.models.collection import Collection
from core.models.event import Event
from core.services.email_service import send_join_summary_email

MAX_DAYS = 7


class Command(BaseCommand):
    help = "Email each group's curators the people who joined it since the last summary"

    def handle(self, *args, **options):
        yesterday = timezone.localdate() - timedelta(days=1)
        earliest = yesterday - timedelta(days=MAX_DAYS - 1)

        # Collections with any sign-up in the widest window: the rest have
        # nothing to say and nothing to claim.
        busy = set(
            Event.objects.filter(
                kind=Event.Kind.MEMBER_JOINED,
                created__date__gte=earliest,
                created__date__lte=yesterday,
            ).values_list("collection_code", flat=True)
        )
        collections = (
            Collection.objects.filter(code__in=busy, status=Collection.Status.ACTIVE)
            .select_related("owner")
            .prefetch_related("co_owners", "invites")
        )

        total = 0
        for collection in collections:
            total += self._summarise(collection, yesterday, earliest)

        self.stdout.write(self.style.SUCCESS(f"Sent {total} join summary emails"))

    def _summarise(self, collection, yesterday, earliest):
        previous = collection.join_summary_sent_on
        if previous is not None and previous >= yesterday:
            return 0
        start = max(previous + timedelta(days=1), earliest) if previous else yesterday

        # Claim the days. The WHERE on the value just read is what makes it hold
        # under concurrency: of two runs that read the same `previous`, only one
        # gets a row back.
        claimed = Collection.objects.filter(
            Q(join_summary_sent_on=previous)
            if previous is not None
            else Q(join_summary_sent_on__isnull=True),
            code=collection.code,
        ).update(join_summary_sent_on=yesterday)
        if not claimed:
            return 0

        members = {u.code: u for u in collection.invites.all()}
        codes = list(
            dict.fromkeys(
                Event.objects.filter(
                    kind=Event.Kind.MEMBER_JOINED,
                    collection_code=collection.code,
                    created__date__gte=start,
                    created__date__lte=yesterday,
                )
                .order_by("created")
                .values_list("actor_code", flat=True)
            )
        )
        joined = [members[c] for c in codes if c in members]

        sent = 0
        failed = False
        for curator in dict.fromkeys([collection.owner, *collection.co_owners.all()]):
            # A curator who joined is not told about themselves.
            names = [u.name for u in joined if u.code != curator.code]
            if not names:
                continue
            try:
                send_join_summary_email(collection, curator, names)
            except Exception as exc:
                failed = True
                self.stderr.write(
                    self.style.WARNING(f"Join summary failed for {collection.code}: {exc}")
                )
                continue
            sent += 1

        # Nothing went out because every send failed: give the days back so the
        # next run tries them again. Once any email is out, the claim stays, or a
        # retry would tell that curator twice.
        if failed and not sent:
            Collection.objects.filter(code=collection.code, join_summary_sent_on=yesterday).update(
                join_summary_sent_on=previous
            )
        return sent

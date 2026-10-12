"""Who has been allowed to run a group here, and what they said to ask.

The product's answer is that an account is enough (`OpenCreatorPolicy`). This
deployment's answer is narrower for the things that carry an obligation to
somebody else — a collection anyone can add to, a thing that has to come back,
a space committed to a stranger for a day — and this table is where that
judgement is recorded.

It lives in this app, not in `core`, and that is the point: **there is no
`is_validated_creator` column on `core.User`.** The state exists only where the
policy that reads it exists, so the schema OIUEEI distributes says nothing about
a gate it does not have, and `core/migrations/` — a log shared by two databases
of the same lineage — never forks.
"""

from datetime import timedelta

from django.db import models
from django.utils import timezone

from core.utils import generate_id


class CreatorValidation(models.Model):
    """One person's request to run a group here, and the answer to it.

    A row exists from the moment somebody asks. There is no row for the people
    who never asked, and their absence is not a rejection — the policy simply
    finds nothing and hands out the open half of the product.
    """

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"

    code = models.CharField(max_length=6, primary_key=True, default=generate_id)

    # One request per person, replacing itself: somebody who asks again after a
    # "no" is having the same conversation, not opening a second file.
    user = models.OneToOneField(
        "core.User",
        on_delete=models.CASCADE,
        related_name="creator_validation",
    )

    # The two questions that actually decide it (oiueei_hosted.md §3). Free text
    # on purpose: the answer in their own words *is* the filter, and a form of
    # checkboxes would collect nothing worth reading.
    who = models.CharField(max_length=512)
    intent = models.CharField(max_length=1024)

    status = models.CharField(
        max_length=8, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    created = models.DateTimeField(default=timezone.now)
    resolved = models.DateTimeField(null=True, blank=True)

    # Why, for the operator's own memory. Never shown to the requester: a
    # written reason invites an argument about rules that are not the product's,
    # and the answer they get is the decision, not its defence.
    note = models.CharField(max_length=512, blank=True, default="")

    class Meta:
        db_table = "hosted_creator_validations"
        ordering = ["-created"]
        verbose_name = "creator validation"

    def __str__(self):
        return f"{self.user_id} ({self.status})"

    @property
    def is_approved(self):
        return self.status == self.Status.APPROVED

    def resolve(self, status, note=""):
        """Approve or reject, stamping when it happened."""
        self.status = status
        self.note = note
        self.resolved = timezone.now()
        self.save(update_fields=["status", "note", "resolved"])
        return self


class Milestone(models.Model):
    """The day a phase of the deployment begins: early adopters, a launch.

    It marks the *start* of a phase. The phase of a week is the one of the last
    milestone dated before that week ends (``date < cutoff``, the cutoff being the
    next Monday), and `PRE` before the first one. A milestone on a Sunday therefore
    belongs to the week that is closing; one on the next Monday, to the following
    week.
    """

    class Phase(models.TextChoices):
        EARLY_ADOPTERS = "EARLY_ADOPTERS", "Early adopters"
        DEV_LAUNCH = "DEV_LAUNCH", "Launch for developers"
        PRODUCT_LAUNCH = "PRODUCT_LAUNCH", "Launch of the product"

    # What a week reports before any milestone exists.
    PRE = "PRE"

    code = models.CharField(max_length=6, primary_key=True, default=generate_id)
    date = models.DateField()
    phase = models.CharField(max_length=14, choices=Phase.choices)
    label = models.CharField(max_length=64)
    note = models.CharField(max_length=256, blank=True, default="")

    class Meta:
        db_table = "hosted_milestones"
        ordering = ["date", "code"]

    def __str__(self):
        return f"{self.date} {self.label}"

    @classmethod
    def phase_of_week(cls, week_start):
        """The phase a week (given by its Monday) belongs to, or `PRE`."""
        cutoff = week_start + timedelta(days=7)
        last = cls.objects.filter(date__lt=cutoff).order_by("-date", "-code").first()
        return last.phase if last else cls.PRE

    @classmethod
    def labels_of_week(cls, week_start):
        """The labels of the milestones that fall inside a week (Monday to Sunday)."""
        end = week_start + timedelta(days=7)
        return list(
            cls.objects.filter(date__gte=week_start, date__lt=end).values_list("label", flat=True)
        )


class WeeklySnapshot(models.Model):
    """One week of the series, kept as aggregates only.

    **No personal data lives here**: counts and medians, never a user code. That is
    why it sits outside the retention periods and survives the anonymisation of the
    `Event` log at fourteen months, which is the reason the table exists. A closed
    week is not recomputed unless the operator asks for it with `--rebuild`.
    """

    class Origin(models.TextChoices):
        LIVE = "LIVE", "Recorded on the Monday it closed"
        BACKFILL = "BACKFILL", "Rebuilt from the event log"

    code = models.CharField(max_length=6, primary_key=True, default=generate_id)
    week_start = models.DateField(unique=True)
    metrics = models.JSONField()
    schema_version = models.PositiveSmallIntegerField()
    origin = models.CharField(max_length=8, choices=Origin.choices)
    computed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "hosted_weekly_snapshots"
        ordering = ["-week_start"]

    def __str__(self):
        return f"week of {self.week_start} ({self.origin})"

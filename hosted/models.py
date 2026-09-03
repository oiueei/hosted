"""Who has been allowed to run a group here, and what they said to ask.

The product's answer is that an account is enough (`OpenCreatorPolicy`). This
deployment's answer is narrower for the two things that carry an obligation to
somebody else — a collection anyone can add to, and a thing that has to come
back — and this table is where that judgement is recorded.

It lives in this app, not in `core`, and that is the point: **there is no
`is_validated_creator` column on `core.User`.** The state exists only where the
policy that reads it exists, so the schema OIUEEI distributes says nothing about
a gate it does not have, and `core/migrations/` — a log shared by two databases
of the same lineage — never forks.
"""

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

from django.db import models
from django.utils import timezone

from core.utils import generate_id

from .user import User


class InAppNotification(models.Model):
    class Type(models.TextChoices):
        BROADCAST = "BROADCAST"
        COLLECTION_DELETED = "COLLECTION_DELETED"
        COLLECTION_REVOKED = "COLLECTION_REVOKED"
        BOOKING_ACCEPTED = "BOOKING_ACCEPTED"
        BOOKING_REJECTED = "BOOKING_REJECTED"
        BOOKING_REQUESTED = "BOOKING_REQUESTED"
        FAQ_QUESTION = "FAQ_QUESTION"
        FAQ_ANSWERED = "FAQ_ANSWERED"
        FAQ_HIDDEN = "FAQ_HIDDEN"
        INVITE_REJECTED = "INVITE_REJECTED"
        MEMBER_LEFT = "MEMBER_LEFT"
        THING_REPORTED = "THING_REPORTED"
        # A member suggested somebody; the owner has to approve before anything
        # is sent. The two answers go back to the proposer — the decline with no
        # reason attached, deliberately.
        #
        # Three types, not two: APPROVED used to be an INVITE_PROPOSED carrying
        # `approved: True`, which meant one type addressed two audiences with
        # opposite meanings ("please decide" to the owner, "they said yes" to the
        # proposer) and no reader could tell them apart without inspecting the
        # payload. Rows written before this split still carry the flag, so the
        # inbox keeps reading it.
        INVITE_PROPOSED = "INVITE_PROPOSED"
        INVITE_PROPOSAL_APPROVED = "INVITE_PROPOSAL_APPROVED"
        INVITE_PROPOSAL_DECLINED = "INVITE_PROPOSAL_DECLINED"

    code = models.CharField(max_length=6, primary_key=True, default=generate_id)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="inbox_notifications")
    type = models.CharField(max_length=32, choices=Type.choices)
    payload = models.JSONField(default=dict)
    created = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "in_app_notifications"
        ordering = ["-created"]

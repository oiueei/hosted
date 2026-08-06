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
        # is sent. INVITE_PROPOSAL_DECLINED goes back to the proposer — with no
        # reason attached, deliberately.
        INVITE_PROPOSED = "INVITE_PROPOSED"
        INVITE_PROPOSAL_DECLINED = "INVITE_PROPOSAL_DECLINED"

    code = models.CharField(max_length=6, primary_key=True, default=generate_id)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="inbox_notifications")
    type = models.CharField(max_length=32, choices=Type.choices)
    payload = models.JSONField(default=dict)
    created = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "in_app_notifications"
        ordering = ["-created"]

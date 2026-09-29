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
        # The owner promoted/demoted a member's co-owner status. No email for
        # either — lightweight, in-app only (v1 simplification): gaining or
        # losing admin power over the group is worth a notice, not a campaign.
        PROMOTED_CO_OWNER = "PROMOTED_CO_OWNER"
        DEMOTED_CO_OWNER = "DEMOTED_CO_OWNER"
        # A member auto-confirmed an on-site reservation (RESERVE_THING) — a
        # notice to the owner, not a question (there is nothing to accept). The
        # cancelled variant reaches whichever party did *not* cancel.
        RESERVATION_MADE = "RESERVATION_MADE"
        RESERVATION_CANCELLED = "RESERVATION_CANCELLED"
        # A hold was accepted or rejected, and the record is for the team that
        # runs the thing — every manager plus whoever decided, never the
        # requester (their own copy is the BOOKING_ACCEPTED/REJECTED above).
        # A request is a question put to whoever runs the thing, and without
        # this its answer only reached the asker: a co-curator's inbox kept a
        # request the founder had already settled, and whoever decided had no
        # trace of their own call. It carries no question, and it is not good
        # or bad news for its readers — a trail, so it renders as info.
        BOOKING_DECIDED = "BOOKING_DECIDED"

    code = models.CharField(max_length=6, primary_key=True, default=generate_id)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="inbox_notifications")
    type = models.CharField(max_length=32, choices=Type.choices)
    payload = models.JSONField(default=dict)
    created = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "in_app_notifications"
        ordering = ["-created"]

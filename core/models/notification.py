from django.db import models
from django.db.models import Q
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

    @classmethod
    def team_booking_notices(cls, queryset=None):
        """The request and reservation notices that reach whoever **manages** them.

        These are the ones the inbox folds into a single summary card once there
        are many of them (``GET /inbox/`` lists them all; ``DELETE
        /inbox/?group=bookings`` dismisses exactly this set). The rule is by
        *who the copy is for*, read from what each producer writes:

        - ``BOOKING_REQUESTED``, ``BOOKING_DECIDED`` and ``RESERVATION_MADE`` only
          ever go to managers of the thing — the requester is excluded from all
          three on purpose;
        - ``RESERVATION_CANCELLED`` goes three ways: to each manager who didn't
          cancel (``cancelled_by_owner`` is ``False``) — the team's; to the
          member whose reservation a manager cancelled (``cancelled_by_owner``
          is ``True``) — theirs, and it links to their own page, not the team's;
          and a record for whoever cancelled (``by_you``), which names the
          member (``member_name``) when a manager cancelled somebody else's —
          the team's — and has none when the member cancelled their own — theirs.

        A copy that is for the person who *had* the reservation is not in this
        set: the summary card links to the team's bookings page, which is not
        theirs. ``frontend/src/utils/inboxGroups.js`` mirrors this rule, and
        ``frontend/src/test/inboxGroupParity.json`` holds the two together.
        """
        types = cls.Type
        team_types = Q(
            type__in=[types.BOOKING_REQUESTED, types.BOOKING_DECIDED, types.RESERVATION_MADE]
        )
        managers_copy = Q(payload__cancelled_by_owner=False)
        managers_own_trace = Q(payload__by_you=True, payload__has_key="member_name")
        cancelled = Q(type=types.RESERVATION_CANCELLED) & (managers_copy | managers_own_trace)
        base = cls.objects.all() if queryset is None else queryset
        return base.filter(team_types | cancelled)

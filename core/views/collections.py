"""
Collection views for OIUEEI.
"""

import csv
import logging
import threading
from collections import Counter
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Count, Prefetch
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.decorators import method_decorator
from django_ratelimit.decorators import ratelimit
from rest_framework import serializers, status
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet

from core.models import RSVP, Collection, InvitationProposal, Thing, User
from core.models.booking import BookingPeriod
from core.models.collection import generate_share_token
from core.models.event import Event
from core.models.notification import InAppNotification
from core.models.transfer import ThingTransfer
from core.permissions import IsCollectionOwner
from core.serializers import (
    CollectionAddThingSerializer,
    CollectionBroadcastSerializer,
    CollectionCreateSerializer,
    CollectionInviteSerializer,
    CollectionProposeInviteSerializer,
    CollectionRemoveInviteSerializer,
    CollectionRemoveThingSerializer,
    CollectionSerializer,
    CollectionUpdateSerializer,
)
from core.serializers.thing import optimise_thing_queryset
from core.services.email_service import (
    send_broadcast_email,
    # Still used directly by the bulk-invite fan-out, which batches its RSVP
    # creation and then mails off the request thread — a different shape from
    # the one-at-a-time `deliver_invitation` path below.
    send_collection_invite_email,
    send_collection_revoke_email,
)
from core.services.invitation_service import (
    _INVITE_QUOTA_MESSAGE,
    _consume_invite_quota,
    _invite_quota_left,
    approve_proposal,
    create_proposal,
    deliver_invitation,
    proposal_approval_blocked,
    reject_proposal,
)
from core.utils import redact_email
from core.validators import SafeHeadlineField
from core.views._helpers import (
    body_dict,
    require_collection_owner,
    type_validity_error,
    viewer_code,
)

logger = logging.getLogger(__name__)


def _optimise_collection_queryset(queryset, viewer=None):
    """Add select/prefetch_related for nested serializer access on collections.

    ``viewer`` is the requesting user, when there is one. It buys the
    ``is_digest_muted`` prefetch, and only then: the field answers False without
    a lookup for anonymous readers and for owners, so prefetching unconditionally
    spends a query on the anonymous PUBLIC-collection read — the hot path that
    costs us the most and gains nothing (pinned by the query-budget tests).

    The prefetch is narrowed to the viewer's own row rather than pulling every
    muted member of the group: the serializer only ever asks "did *I* mute this?"
    """
    queryset = queryset.select_related("owner").prefetch_related(
        "invites",
        Prefetch("things", queryset=optimise_thing_queryset(Thing.objects.all())),
    )
    if viewer is not None and viewer.is_authenticated:
        queryset = queryset.prefetch_related(
            Prefetch("digest_muted", queryset=User.objects.filter(code=viewer.code)),
            # Owner-only in the serializer, but prefetched for any signed-in
            # viewer: the alternative is a query per collection on the owner's
            # own list (caught by the query-budget tests). The proposer is
            # joined because the card prints their name.
            Prefetch(
                "invitation_proposals",
                queryset=InvitationProposal.objects.filter(
                    status=InvitationProposal.Status.PENDING
                ).select_related("proposer"),
                to_attr="_pending_proposals",
            ),
        )
    return queryset


class CollectionViewSet(ModelViewSet):
    """
    ViewSet for Collection CRUD operations.

    list:    GET /api/v1/collections/
    create:  POST /api/v1/collections/
    retrieve: GET /api/v1/collections/{code}/
    update:  PUT /api/v1/collections/{code}/
    destroy: DELETE /api/v1/collections/{code}/
    add_thing: POST /api/v1/collections/{code}/add-thing/
    """

    lookup_field = "code"

    def get_queryset(self):
        qs = Collection.objects.filter(owner=self.request.user).order_by("-created")
        if self.action in ("list", "retrieve"):
            # The viewer matters here even though this list is always their own:
            # `pending_proposals` is owner-only, so this is exactly the list that
            # needs its prefetch, and without it the field costs one query per
            # collection (caught by the query-budget tests).
            return _optimise_collection_queryset(qs, viewer=self.request.user)
        return qs

    def get_serializer_class(self):
        if self.action == "create":
            return CollectionCreateSerializer
        if self.action in ("update", "partial_update"):
            return CollectionUpdateSerializer
        if self.action == "add_thing":
            return CollectionAddThingSerializer
        return CollectionSerializer

    def get_permissions(self):
        # remove_thing is intentionally NOT gated by IsCollectionOwner here: its
        # rule is broader (in COMMUNITY mode a thing's own owner may remove it), so
        # it is enforced inline in the action. It also fetches via get_object_or_404,
        # so an object-level permission would never run for it anyway (the I3 footgun).
        if self.action in ("update", "partial_update", "destroy"):
            return [IsAuthenticated(), IsCollectionOwner()]
        # Anonymous read is allowed for retrieve; can_view() (below) still gates
        # it — only PUBLIC, ACTIVE collections are visible without membership.
        if self.action == "retrieve":
            return [AllowAny()]
        return [IsAuthenticated()]

    def get_object(self):
        if self.action == "retrieve":
            # Use the optimised queryset (prefetch + annotations) so nesting the
            # collection's things doesn't N+1. No owner filter — can_view() below
            # gates access so invited (non-owner) users can still retrieve.
            qs = _optimise_collection_queryset(Collection.objects.all(), viewer=self.request.user)
            obj = get_object_or_404(qs, code=self.kwargs[self.lookup_field])
            if not obj.can_view(viewer_code(self.request)):
                self.permission_denied(self.request)
            return obj
        obj = get_object_or_404(Collection, code=self.kwargs[self.lookup_field])
        self.check_object_permissions(self.request, obj)
        return obj

    def perform_destroy(self, instance):
        owner_name = instance.owner.display_name
        headline = instance.headline
        invitees = list(instance.invites.all())

        orphaned_things = instance.things.annotate(col_count=Count("collections")).filter(
            col_count=1
        )
        collection_code = instance.code  # snapshot before delete() nulls the PK
        with transaction.atomic():
            orphaned_things.delete()
            instance.delete()

        Event.log(
            Event.Kind.COLLECTION_DELETED,
            actor=self.request.user,
            collection=collection_code,
        )

        InAppNotification.objects.bulk_create(
            [
                InAppNotification(
                    user=invitee,
                    type=InAppNotification.Type.COLLECTION_DELETED,
                    payload={"collection_headline": headline, "owner_name": owner_name},
                )
                for invitee in invitees
            ]
        )

    def perform_create(self, serializer):
        validated_data = serializer.validated_data
        collection = Collection.objects.create(
            owner=self.request.user,
            **validated_data,
        )
        Event.log(Event.Kind.COLLECTION_CREATED, actor=self.request.user, collection=collection)
        self._created_collection = collection

    @method_decorator(ratelimit(key="user", rate="30/h", method="POST", block=True))
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return Response(
            CollectionSerializer(self._created_collection, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"], url_path="add-thing")
    @method_decorator(ratelimit(key="user", rate="60/h", method="POST", block=True))
    def add_thing(self, request, code=None):
        """Add a thing to the collection.

        Owner can always add. Invited users can add their own things
        in COMMUNITY mode collections.
        """
        collection = get_object_or_404(Collection, code=self.kwargs[self.lookup_field])

        if not collection.can_add_thing(request.user.code):
            return Response(
                {"error": "You do not have permission to add things to this collection"},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = CollectionAddThingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        thing_code = serializer.validated_data["thing_code"]
        thing = get_object_or_404(Thing, code=thing_code)

        if not thing.is_owner(request.user.code):
            return Response(
                {"error": "You can only add your own things to collections"},
                status=status.HTTP_403_FORBIDDEN,
            )

        if collection.things.filter(code=thing_code).exists():
            return Response(
                {"error": "Thing is already in this collection"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # The thing's type must be valid for this collection — same rules as
        # create/update, so add-thing can't smuggle in a forbidden type (L4).
        type_error = type_validity_error(thing.type, collection)
        if type_error:
            return Response({"error": type_error}, status=status.HTTP_400_BAD_REQUEST)

        # Mass-upload ceiling. This path moves an existing thing rather than
        # creating one, but it lands in the same collection and must not be the
        # way around the guard.
        full = collection.capacity_violation("things", adding=1)
        if full:
            return Response({"error": full}, status=status.HTTP_400_BAD_REQUEST)

        collection.things.add(thing)
        collection.note_capacity("things")

        return Response(
            {
                "message": "Thing added to collection",
                "collection": CollectionSerializer(collection, context={"request": request}).data,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"], url_path="remove-thing")
    def remove_thing(self, request, code=None):
        """Remove a thing from the collection (without deleting it).

        Owner can remove any thing. In COMMUNITY mode, thing owners
        can remove their own things.
        """
        collection = get_object_or_404(Collection, code=self.kwargs[self.lookup_field])

        serializer = CollectionRemoveThingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        thing_code = serializer.validated_data["thing_code"]

        thing = collection.things.filter(code=thing_code).first()
        if thing is None:
            return Response(
                {"error": "Thing is not in this collection"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Collection owner can always remove. In community mode,
        # thing owners can remove their own things.
        if not collection.is_owner(request.user.code):
            if not (collection.is_community() and thing.is_owner(request.user.code)):
                return Response(
                    {"error": "You do not have permission to remove this thing"},
                    status=status.HTTP_403_FORBIDDEN,
                )

        collection.things.remove(thing)

        return Response(
            {
                "message": "Thing removed from collection",
                "collection": CollectionSerializer(collection, context={"request": request}).data,
            },
            status=status.HTTP_200_OK,
        )


# Daily cap on invitation *emails* per account, shared by the single and bulk
# invite endpoints. The per-view rate limits count requests, and one bulk request
# fans out up to MAX_ROWS emails — 5/h x 100 rows is ~500 owner-authored emails
# an hour from a free pop-in account, a spam/phishing vector riding the
# deployment's sending domain. This counts the emails themselves.
#
# **Operator policy, not a product rule.** The cap protects the deployment's own
# sending reputation, and only the operator knows what their provider tolerates,
# so the value lives in settings (`INVITE_EMAILS_PER_DAY`, read from the env in
# base.py) and the standalone ships it **unset = unlimited**: a self-hoster
# decides for their own instance. www.oiueei.com sets the config var.
#
# Coarse abuse prevention, not an exact quota: it also follows RATELIMIT_ENABLE
# (the same switch the django-ratelimit decorators read, so dev and tests stay
# consistent) and its DatabaseCache read-then-set shares base.py's I7
# non-atomicity note.
class CollectionInviteView(APIView):
    """
    POST /api/v1/collections/{collection_code}/invite/
    Invite a user to a collection.

    DELETE /api/v1/collections/{collection_code}/invite/
    Remove a user from the collection's invite list.
    """

    permission_classes = [IsAuthenticated]

    @method_decorator(ratelimit(key="user", rate="30/h", method="POST", block=True))
    def post(self, request, collection_code):
        collection = get_object_or_404(Collection, code=collection_code)

        denied = require_collection_owner(
            collection, request.user.code, "Only the owner can invite users"
        )
        if denied:
            return denied

        # Checked before get_or_create so a quota-blocked request creates no User row.
        if _invite_quota_left(request.user.code) == 0:
            return Response(
                {"error": _INVITE_QUOTA_MESSAGE},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        serializer = CollectionInviteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"].lower()

        # Member ceiling, enforced where invitations are SENT rather than where
        # they are accepted: refusing an invitee at the door would punish someone
        # who did nothing wrong. It counts current members, so invitations still
        # pending are not included — the daily email quota above is what caps a
        # fan-out of unaccepted invites.
        #
        # Someone who is already a member consumes no capacity — they are inside
        # the count the ceiling measures — so re-inviting them is never a ceiling
        # refusal: it falls through to the "already invited" 400 below, which is
        # the accurate answer. Checked by email so it still runs before
        # get_or_create, leaving a refused invite with no User row behind.
        if (
            collection.capacity_ceiling("invites")
            and not collection.invites.filter(email=email).exists()
        ):
            full = collection.capacity_violation("invites", adding=1)
            if full:
                return Response({"error": full}, status=status.HTTP_400_BAD_REQUEST)

        # One delivery path, shared with an owner approving a member's proposal
        # (invitation_service.deliver_invitation): the get_or_create, the RSVP
        # pair, the email and the quota all live there, so the two routes into an
        # invitation cannot drift.
        invited_user, already_invited = deliver_invitation(
            collection,
            email,
            request.user.display_name,
            quota_user_code=request.user.code,
        )
        if already_invited:
            return Response(
                {"detail": "This user is already invited to this collection."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {
                "message": "Invitation sent",
                "email": email,
                "user_code": invited_user.code,
            },
            status=status.HTTP_200_OK,
        )

    def delete(self, request, collection_code):
        collection = get_object_or_404(Collection, code=collection_code)

        denied = require_collection_owner(
            collection, request.user.code, "Only the owner can remove invites"
        )
        if denied:
            return denied

        serializer = CollectionRemoveInviteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user_code = serializer.validated_data["user_code"]

        # Check if user is a confirmed invite
        try:
            invited_user = collection.invites.get(code=user_code)
        except User.DoesNotExist:
            invited_user = None

        if invited_user:
            collection.invites.remove(invited_user)
            Event.log(Event.Kind.MEMBER_LEFT, actor=invited_user, collection=collection)

            # Notify the removed user — invited_user is already in hand (fetched
            # above), so there's no need to re-query and no DoesNotExist to guard.
            owner_name = request.user.display_name
            send_collection_revoke_email(
                owner_name, collection.headline, invited_user.email, collection=collection
            )
            InAppNotification.objects.create(
                user=invited_user,
                type=InAppNotification.Type.COLLECTION_REVOKED,
                payload={"collection_headline": collection.headline, "owner_name": owner_name},
            )

            return Response(
                {
                    "message": "User removed from collection",
                    "user_code": user_code,
                },
                status=status.HTTP_200_OK,
            )

        # Check if user has a pending invite (RSVP)
        pending_rsvps = RSVP.objects.filter(
            user_code_id=user_code,
            target_code=collection_code,
            action__in=[RSVP.Action.COLLECTION_INVITE, RSVP.Action.COLLECTION_REJECT],
        )
        if pending_rsvps.exists():
            pending_rsvps.delete()
            return Response(
                {
                    "message": "Pending invitation cancelled",
                    "user_code": user_code,
                },
                status=status.HTTP_200_OK,
            )

        return Response(
            {"error": "User is not invited to this collection"},
            status=status.HTTP_400_BAD_REQUEST,
        )


class CollectionLeaveView(APIView):
    """
    POST /api/v1/collections/{collection_code}/leave/
    Lets an invited member remove themselves from a collection (self-unlink). The
    owner cannot leave their own collection — they delete it instead.
    """

    permission_classes = [IsAuthenticated]

    @method_decorator(ratelimit(key="user", rate="30/h", method="POST", block=True))
    def post(self, request, collection_code):
        collection = get_object_or_404(Collection, code=collection_code)

        if collection.is_owner(request.user.code):
            return Response(
                {"detail": "The owner can't leave their own collection."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not collection.invites.filter(code=request.user.code).exists():
            return Response(
                {"detail": "You are not a member of this collection."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        collection.invites.remove(request.user)
        Event.log(Event.Kind.MEMBER_LEFT, actor=request.user, collection=collection)

        # Let the owner know a member left (in-app; symmetric to the revoke notice).
        InAppNotification.objects.create(
            user=collection.owner,
            type=InAppNotification.Type.MEMBER_LEFT,
            payload={
                "collection_headline": collection.headline,
                "member_name": request.user.display_name,
                "collection_code": collection.code,
            },
        )

        return Response(
            {"message": "You have left the collection"},
            status=status.HTTP_200_OK,
        )


class CollectionProposeInviteView(APIView):
    """
    POST /api/v1/collections/{collection_code}/invite/propose/

    A **member** asks the owner to invite somebody. Nothing is sent to the
    proposed address here — see `invitation_service.create_proposal`.

    Members could not bring anyone in at all before this: every new person cost
    an owner action, so a group grew only as fast as one person worked at it. But
    an owner is not merely a bottleneck: the group may be closed, may run on
    subscriptions, papers or rules of admission the product knows nothing about.
    So the member proposes and the owner decides.

    Open in **both** modes. PROPRIETARY decides who may add a *thing*; it has
    never decided who may suggest a person, and the owner's approval is the gate
    either way.

    Rate limited 30/day per member — high on purpose. This is not expected to be
    abused, and if somebody does, the owner has a much better answer than a quota:
    removing them from the collection.
    """

    permission_classes = [IsAuthenticated]

    @method_decorator(ratelimit(key="user", rate="30/d", method="POST", block=True))
    def post(self, request, collection_code):
        collection = get_object_or_404(Collection, code=collection_code)

        if collection.is_owner(request.user.code):
            # Owners have the real thing one endpoint over.
            return Response(
                {"detail": "You own this collection — invite them directly."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not collection.invites.filter(code=request.user.code).exists():
            return Response(
                {"detail": "Only members can propose someone."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not collection.allow_member_proposals:
            # The owner has said they don't want to be asked. The frontend hides
            # the form, so reaching this means a stale page or a direct POST.
            return Response(
                {"detail": "This group doesn't take suggestions from members."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = CollectionProposeInviteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"].lower()
        note = serializer.validated_data.get("note", "")

        # Answered here rather than by the owner: these need no decision, and
        # they must not tell the proposer anything they couldn't already see.
        # Membership is visible to members, so "already a member" is safe.
        if collection.invites.filter(email=email).exists():
            return Response(
                {"detail": "They are already part of this group."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if InvitationProposal.objects.filter(
            collection=collection, email=email, status=InvitationProposal.Status.PENDING
        ).exists():
            return Response(
                {"detail": "Someone has already suggested them — it's with the owner."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        create_proposal(collection, request.user, email, note)
        return Response(
            {"message": "Suggestion sent to the owner"},
            status=status.HTTP_200_OK,
        )


class CollectionProposalActionView(APIView):
    """
    POST /api/v1/proposals/{proposal_code}/{approve|reject}/

    The owner's in-app answer to a member's suggestion; the email links reach the
    same decisions through `VerifyLinkView`. Owner only — the proposer must not
    be able to wave their own suggestion through.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, proposal_code, action):
        proposal = get_object_or_404(InvitationProposal, code=proposal_code)

        denied = require_collection_owner(
            proposal.collection, request.user.code, "Only the owner can answer a suggestion"
        )
        if denied:
            return denied

        if not proposal.is_valid():
            return Response(
                {"detail": "This suggestion is no longer pending."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if action == "approve":
            # The ceiling and the quota are the owner's, and are checked for the
            # same reason the direct invite checks them: an approval that can't
            # be delivered should say so rather than half-happen. Shared with the
            # emailed approve link, which must not be a way around either.
            blocked = proposal_approval_blocked(proposal)
            if blocked:
                reason, code = blocked
                return Response({"error": reason}, status=code)
            approve_proposal(proposal)
            return Response({"message": "Invitation sent"}, status=status.HTTP_200_OK)

        reject_proposal(proposal)
        return Response({"message": "Suggestion declined"}, status=status.HTTP_200_OK)


class CollectionDigestPrefView(APIView):
    """
    POST /api/v1/collections/{collection_code}/digest/  {"muted": true|false}

    A member silences (or un-silences) this one group's digest. It is the narrow
    control that makes ``User.notify_news`` defaulting to True honest: leaving a
    chatty group's summaries costs nothing else, so nobody has to choose between
    a weekly digest they didn't ask for and the booking emails they need.

    Members only. The owner never receives their own collection's digest (it goes
    to ``invites``), so there is nothing here for them to mute — they change the
    frequency on the collection instead.

    Idempotent: ``add``/``remove`` on the M2M, so a double POST is harmless and
    the email footer's one-click link can be followed twice without an error.
    """

    permission_classes = [IsAuthenticated]

    @method_decorator(ratelimit(key="user", rate="30/h", method="POST", block=True))
    def post(self, request, collection_code):
        collection = get_object_or_404(Collection, code=collection_code)

        if not collection.invites.filter(code=request.user.code).exists():
            return Response(
                {"detail": "You are not a member of this collection."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        muted = body_dict(request).get("muted")
        if not isinstance(muted, bool):
            return Response(
                {"muted": ["This field is required and must be true or false."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if muted:
            collection.digest_muted.add(request.user)
        else:
            collection.digest_muted.remove(request.user)

        return Response({"muted": muted}, status=status.HTTP_200_OK)


def _send_bulk_invites(inviter_name, headline, recipients, collection=None):
    """Send the collection-invite emails for a bulk invite without blocking.

    In production (``EMAIL_SEND_ASYNC``) the whole loop runs on a daemon thread so
    a large batch doesn't stall the response; elsewhere it sends synchronously to
    keep tests deterministic. Each send is best-effort and swallows its errors.
    """
    if not recipients:
        return

    def _run():
        for email, accept_link, reject_link in recipients:
            try:
                send_collection_invite_email(
                    inviter_name, headline, email, accept_link, reject_link, collection=collection
                )
            except Exception:
                # Per-email SMTP failures are already handled inside _send; anything
                # reaching here is unexpected (e.g. a template/programming error).
                # Log it (redacted per M5) instead of silently dropping the invite,
                # but keep going so one bad row can't abort the rest of the batch.
                logger.warning(
                    "Bulk invite email failed for %s", redact_email(email), exc_info=True
                )

    if getattr(settings, "EMAIL_SEND_ASYNC", False):
        threading.Thread(target=_run, daemon=True).start()
    else:
        _run()


def _send_broadcast(
    owner_name, owner_email, headline, collection_code, message, emails, collection=None
):
    """Send a collection broadcast without blocking the request.

    ``send_broadcast_email`` loops over every invitee with a sequential SMTP call
    (10s timeout each), so a large group could exhaust the Heroku 30s request
    window (H12). In production (``EMAIL_SEND_ASYNC``) run it on a daemon thread so
    the owner's response returns immediately; elsewhere send synchronously to keep
    tests deterministic. It already swallows per-recipient send errors.
    """

    def _run():
        send_broadcast_email(
            owner_name=owner_name,
            owner_email=owner_email,
            collection_headline=headline,
            collection_code=collection_code,
            message=message,
            emails=emails,
            collection=collection,
        )

    if getattr(settings, "EMAIL_SEND_ASYNC", False):
        threading.Thread(target=_run, daemon=True).start()
    else:
        _run()


class CollectionBulkInviteView(APIView):
    """
    POST /api/v1/collections/{collection_code}/invite/bulk/

    Invite many guests at once from a client-parsed CSV
    (``{"invites": [{"email": ..., "name": ...?}, ...]}``). Best-effort: valid,
    new addresses are invited and emailed; the rest are reported as skipped with a
    reason (invalid / duplicate / already_member / already_invited) — one bad row
    never fails the batch. Owner-only, capped at ``MAX_ROWS`` and rate-limited.
    """

    permission_classes = [IsAuthenticated]
    MAX_ROWS = 100

    @method_decorator(ratelimit(key="user", rate="5/h", method="POST", block=True))
    def post(self, request, collection_code):
        collection = get_object_or_404(Collection, code=collection_code)

        denied = require_collection_owner(
            collection, request.user.code, "Only the owner can invite users"
        )
        if denied:
            return denied

        # None = unlimited (RATELIMIT_ENABLE off in dev/tests). Exhausted → 429
        # outright; a partially-available quota lets the batch run and reports the
        # overflow per row below, so the owner sees exactly which addresses wait.
        quota_left = _invite_quota_left(request.user.code)
        if quota_left == 0:
            return Response(
                {"error": _INVITE_QUOTA_MESSAGE},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        rows = body_dict(request).get("invites")
        if not isinstance(rows, list) or not rows:
            return Response({"error": "No emails to invite."}, status=status.HTTP_400_BAD_REQUEST)
        if len(rows) > self.MAX_ROWS:
            return Response(
                {"error": f"At most {self.MAX_ROWS} invitations can be sent at once."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        email_field = serializers.EmailField(max_length=64)
        name_field = SafeHeadlineField(max_length=32, required=False, allow_blank=True)

        skipped = []
        seen = set()
        candidates = []  # (email, name) — well-formed and unique within the batch
        for row in rows:
            raw_email = (row.get("email") if isinstance(row, dict) else "") or ""
            try:
                email = email_field.run_validation(str(raw_email).strip()).lower()
            except serializers.ValidationError:
                skipped.append({"email": str(raw_email).strip()[:64], "reason": "invalid"})
                continue
            if email in seen:
                skipped.append({"email": email, "reason": "duplicate"})
                continue
            seen.add(email)
            raw_name = str((row.get("name") if isinstance(row, dict) else "") or "").strip()
            try:
                # A malformed name (e.g. HTML) is dropped, not a reason to skip.
                name = name_field.run_validation(raw_name) if raw_name else ""
            except serializers.ValidationError:
                name = ""
            candidates.append((email, name))

        # Member ceiling for the whole batch — same reasoning as the single
        # endpoint, and checked against the batch so a bulk invite cannot step
        # over the line 100 rows at a time. Counted AFTER validation and dedup,
        # and excluding addresses that are ALREADY members: those sit inside the
        # count the ceiling is measured against, so counting them again would
        # refuse a batch that adds nobody. With no ceiling set — the standalone
        # default — none of this runs and the guard costs no query.
        #
        # No row lock here, unlike the thing ceiling: this endpoint sends
        # invitations, it does not add members. The count it reads only moves
        # when someone accepts, which is deliberately never refused, so two
        # concurrent batches have nothing to race over.
        if collection.capacity_ceiling("invites"):
            emails = [email for email, _ in candidates]
            already = set(
                collection.invites.filter(email__in=emails).values_list("email", flat=True)
            )
            full = collection.capacity_violation(
                "invites", adding=sum(1 for email in emails if email not in already)
            )
            if full:
                return Response({"error": full}, status=status.HTTP_400_BAD_REQUEST)

        inviter_name = request.user.display_name
        invited = []
        recipients = []  # (email, accept_link, reject_link)
        with transaction.atomic():
            for email, name in candidates:
                # Past today's cap: report the rest of the batch per row (the
                # frontend shows the reason) rather than silently dropping it.
                # Before get_or_create, so a quota-skipped row creates no User.
                if quota_left is not None and len(invited) >= quota_left:
                    skipped.append({"email": email, "reason": "daily_limit"})
                    continue
                defaults = {"email": email}
                if name:
                    defaults["name"] = name
                invited_user, created = User.objects.get_or_create(email=email, defaults=defaults)
                if created:
                    Event.log(Event.Kind.USER_JOINED, actor=invited_user)

                if collection.is_invited(invited_user.code):
                    skipped.append({"email": email, "reason": "already_member"})
                    continue
                if RSVP.objects.filter(
                    user_code=invited_user,
                    target_code=collection_code,
                    action=RSVP.Action.COLLECTION_INVITE,
                ).exists():
                    skipped.append({"email": email, "reason": "already_invited"})
                    continue

                accept_rsvp = RSVP.objects.create(
                    user_code=invited_user,
                    user_email=email,
                    action=RSVP.Action.COLLECTION_INVITE,
                    target_code=collection_code,
                )
                reject_rsvp = RSVP.objects.create(
                    user_code=invited_user,
                    user_email=email,
                    action=RSVP.Action.COLLECTION_REJECT,
                    target_code=collection_code,
                )
                invited.append(email)
                recipients.append((email, accept_rsvp.action_link(), reject_rsvp.action_link()))

        _consume_invite_quota(request.user.code, len(invited))
        _send_bulk_invites(inviter_name, collection.headline, recipients, collection=collection)

        logger.info(
            "Bulk invite: user=%s collection=%s invited=%d skipped=%d",
            request.user.code,
            collection_code,
            len(invited),
            len(skipped),
        )

        return Response(
            {"invited": len(invited), "skipped": skipped, "total": len(rows)},
            status=status.HTTP_200_OK,
        )


class CollectionStatsView(APIView):
    """
    GET /api/v1/collections/{collection_code}/stats/

    Owner-only usage statistics for any collection, returned as a CSV
    download (metric,value): a snapshot plus a 90-day window, and — since the
    optional member demographics exist — an aggregate age-range and postal-code
    breakdown. Aggregate only; the per-member values live on the guests page
    (and stay COMMUNITY-only there).
    """

    permission_classes = [IsAuthenticated]
    WINDOW_DAYS = 90

    def get(self, request, collection_code):
        collection = get_object_or_404(Collection, code=collection_code)
        denied = require_collection_owner(
            collection, request.user.code, "Only the owner can view stats"
        )
        if denied:
            return denied

        win = self.WINDOW_DAYS
        since = timezone.now() - timedelta(days=win)
        since_date = since.date()
        members = list(collection.invites.all())
        member_codes = [u.code for u in members]

        rows = [["metric", "value"]]
        rows.append(["Members", len(members)])
        rows.append(
            [
                "Pending invitations",
                RSVP.objects.filter(
                    action=RSVP.Action.COLLECTION_INVITE, target_code=collection_code
                ).count(),
            ]
        )
        rows.append(["Things total", collection.things.count()])
        rows.append(["Things active", collection.things.filter(status=Thing.Status.ACTIVE).count()])
        rows.append(
            ["Things reserved", collection.things.filter(status=Thing.Status.TAKEN).count()]
        )
        rows.append(
            [f"Things added ({win}d)", collection.things.filter(created__gte=since).count()]
        )
        rows.append(
            [
                f"Bookings ({win}d)",
                BookingPeriod.objects.filter(thing_code__collections=collection, created__gte=since)
                .distinct()
                .count(),
            ]
        )
        rows.append(
            [
                f"Handovers ({win}d)",
                ThingTransfer.objects.filter(
                    thing__collections=collection, lent_date__gte=since_date
                )
                .distinct()
                .count(),
            ]
        )
        rows.append(
            [
                f"Invitations sent ({win}d)",
                RSVP.objects.filter(
                    action=RSVP.Action.COLLECTION_INVITE,
                    target_code=collection_code,
                    created__gte=since,
                ).count(),
            ]
        )
        active = set(
            Thing.objects.filter(
                collections=collection, created__gte=since, owner_id__in=member_codes
            ).values_list("owner_id", flat=True)
        ) | set(
            BookingPeriod.objects.filter(
                thing_code__collections=collection,
                created__gte=since,
                requester_code_id__in=member_codes,
            ).values_list("requester_code_id", flat=True)
        )
        rows.append([f"Active members ({win}d)", len(active)])

        age_labels = {
            "PRE_1946": "Born 1945 or earlier",
            "BOOMER": "Born 1946-1964 (Boomers)",
            "GEN_X": "Born 1965-1980 (Gen X)",
            "GEN_Y": "Born 1981-1996 (Millennials)",
            "GEN_Z": "Born 1997-2012 (Gen Z)",
            "GEN_A": "Born 2013-2024 (Gen Alpha)",
            "GEN_B": "Born 2025-2039 (Gen Beta)",
        }
        age_counts = Counter(u.age_range for u in members if u.age_range)
        for age_code, label in age_labels.items():
            rows.append([label, age_counts.get(age_code, 0)])
        rows.append(["Birth year not specified", sum(1 for u in members if not u.age_range)])

        postal_counts = Counter(u.postal_code for u in members if u.postal_code)
        for postal, count in postal_counts.most_common(10):
            # The code follows the literal "Postal " label, so the cell never
            # starts with =, +, - or @ — no spreadsheet-formula injection.
            rows.append([f"Postal {postal}", count])
        rows.append(["Postal not specified", sum(1 for u in members if not u.postal_code)])

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="{collection_code}-stats.csv"'
        csv.writer(response).writerows(rows)
        return response


class InvitedCollectionsView(APIView):
    """
    GET /api/v1/invited-collections/
    List collections where the current user is in invites.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        invited_collections = _optimise_collection_queryset(
            request.user.invited_to_collections.filter(status=Collection.Status.ACTIVE),
            viewer=request.user,
        ).order_by("owner__name", "created")
        serializer = CollectionSerializer(
            invited_collections, many=True, context={"request": request}
        )
        return Response(serializer.data)


class MyPendingInvitationsView(APIView):
    """
    GET /api/v1/my-invitations/
    List pending (not yet accepted) collection invitations for the current user.
    Returns accept + reject RSVP codes, collection headline and owner name.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Only surface invitations whose link is still valid (matches the per-action
        # expiry in RSVP.is_valid / cleanup_rsvps), so a stale invite never shows a
        # link that would 401 on click.
        cutoff = timezone.now() - timedelta(
            hours=RSVP.expiry_hours_for(RSVP.Action.COLLECTION_INVITE)
        )
        accept_rsvps = list(
            RSVP.objects.filter(
                user_code=request.user,
                action=RSVP.Action.COLLECTION_INVITE,
                created__gte=cutoff,
            )
        )

        if not accept_rsvps:
            return Response([])

        target_codes = [r.target_code for r in accept_rsvps]

        # Fetch all related collections and reject RSVPs in two queries
        collections_by_code = {
            c.code: c
            for c in Collection.objects.filter(code__in=target_codes).select_related("owner")
        }
        reject_rsvps_by_target = {
            r.target_code: r
            for r in RSVP.objects.filter(
                user_code=request.user,
                action=RSVP.Action.COLLECTION_REJECT,
                target_code__in=target_codes,
            )
        }

        result = []
        for accept_rsvp in accept_rsvps:
            collection = collections_by_code.get(accept_rsvp.target_code)
            if collection is None:
                continue
            reject_rsvp = reject_rsvps_by_target.get(accept_rsvp.target_code)
            result.append(
                {
                    # The high-entropy token, not the 6-char PK — the frontend
                    # feeds these straight to /verify/<value>/, which now resolves
                    # RSVPs by token only.
                    "accept_code": accept_rsvp.token,
                    "reject_code": reject_rsvp.token if reject_rsvp else None,
                    "collection_code": collection.code,
                    "collection_headline": collection.headline,
                    "owner_name": collection.owner.display_name,
                }
            )

        return Response(result)


class CollectionShareLinkView(APIView):
    """
    POST /api/v1/collections/{collection_code}/share-link/
    Generate (or rotate) a public share token. Returns the full public URL.

    DELETE /api/v1/collections/{collection_code}/share-link/
    Revoke the share token. The link becomes invalid for everyone.

    Owner only. Token is a 22-char URL-safe bearer credential — anyone with
    the link can join the collection via /share/{token}, so the token must
    not appear in any read endpoint.
    """

    permission_classes = [IsAuthenticated]

    @method_decorator(ratelimit(key="user", rate="30/h", method="POST", block=True))
    def post(self, request, collection_code):
        collection = get_object_or_404(Collection, code=collection_code)

        denied = require_collection_owner(
            collection, request.user.code, "Only the owner can manage the share link"
        )
        if denied:
            return denied

        rotate = bool(body_dict(request).get("rotate"))

        if rotate or not collection.share_token:
            collection.share_token = generate_share_token()
            collection.save(update_fields=["share_token"])

        share_base = getattr(settings, "SHARE_LINK_BASE_URL", "http://localhost:3000/share")
        share_url = f"{share_base}/{collection.share_token}"

        return Response(
            {
                "share_url": share_url,
                "share_token": collection.share_token,
            },
            status=status.HTTP_200_OK,
        )

    def delete(self, request, collection_code):
        collection = get_object_or_404(Collection, code=collection_code)

        denied = require_collection_owner(
            collection, request.user.code, "Only the owner can manage the share link"
        )
        if denied:
            return denied

        if collection.share_token:
            collection.share_token = None
            collection.save(update_fields=["share_token"])

        return Response(
            {"message": "Share link revoked"},
            status=status.HTTP_200_OK,
        )


class CollectionBroadcastView(APIView):
    """
    POST /api/v1/collections/{collection_code}/broadcast/
    Send a broadcast email from the collection owner to all invitees.
    """

    permission_classes = [IsAuthenticated]

    @method_decorator(ratelimit(key="user", rate="5/d", method="POST", block=True))
    def post(self, request, collection_code):
        collection = get_object_or_404(Collection, code=collection_code)

        denied = require_collection_owner(
            collection, request.user.code, "Only the owner can send broadcasts"
        )
        if denied:
            return denied

        serializer = CollectionBroadcastSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        message = serializer.validated_data["message"]

        # Gather invitee emails
        invitee_emails = list(collection.invites.values_list("email", flat=True))

        if not invitee_emails:
            return Response(
                {"error": "No invitees to broadcast to"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        owner_name = request.user.display_name

        _send_broadcast(
            owner_name=owner_name,
            owner_email=request.user.email,
            headline=collection.headline,
            collection_code=collection.code,
            message=message,
            emails=invitee_emails,
            collection=collection,
        )

        InAppNotification.objects.bulk_create(
            [
                InAppNotification(
                    user=invitee,
                    type=InAppNotification.Type.BROADCAST,
                    payload={
                        "collection_headline": collection.headline,
                        "owner_name": owner_name,
                        "message": message,
                        "collection_code": collection.code,
                    },
                )
                for invitee in collection.invites.all()
            ]
        )

        return Response(
            {
                "message": "Broadcast sent",
                "recipients": len(invitee_emails),
            },
            status=status.HTTP_200_OK,
        )

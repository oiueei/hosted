"""Sending a collection invitation, and the member-proposal flow around it.

`deliver_invitation` is the single place an invitation actually goes out. Both
callers reach it: the owner inviting directly (`CollectionInviteView`) and an
owner approving a member's proposal. An approved proposal is therefore
indistinguishable from an owner's own invite — same RSVP pair, same email, same
quota — which is the point. Two code paths would drift, and the one used less
often is the one that would rot.
"""

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from core.models import RSVP, InvitationProposal, User
from core.models.event import Event
from core.models.notification import InAppNotification
from core.services.email_service import (
    send_collection_invite_email,
    send_invitation_proposal_email,
    send_proposal_declined_email,
)

# ── The daily invitation-email quota ────────────────────────────────────────
# Lives here rather than in the views because both senders are here now, and a
# service reaching back into a view for it was a layering inversion. The views
# import these.
_INVITE_QUOTA_TTL = 60 * 60 * 24  # ~24h; the date is in the key, so it rolls over anyway.
_INVITE_QUOTA_MESSAGE = "Daily invitation limit reached. Try again tomorrow."


def _invite_quota_cap():
    """Configured daily cap, or ``None`` when the quota is off.

    Off means either the whole rate-limiting layer is disabled (dev, tests) or
    the operator left the cap unset/zero — the standalone default.
    """
    if not getattr(settings, "RATELIMIT_ENABLE", True):
        return None
    cap = getattr(settings, "INVITE_EMAILS_PER_DAY", 0) or 0
    return cap if cap > 0 else None


def _invite_quota_key(user_code):
    return f"invq:{user_code}:{timezone.localdate().isoformat()}"


def _invite_quota_left(user_code):
    """Invitation emails this account may still send today; ``None`` = unlimited."""
    cap = _invite_quota_cap()
    if cap is None:
        return None
    return max(cap - cache.get(_invite_quota_key(user_code), 0), 0)


def _consume_invite_quota(user_code, count):
    """Record ``count`` invitation emails against today's quota."""
    if count <= 0 or _invite_quota_cap() is None:
        return
    key = _invite_quota_key(user_code)
    cache.set(key, cache.get(key, 0) + count, _INVITE_QUOTA_TTL)


def proposal_approval_blocked(proposal):
    """Why this approval cannot be delivered right now, or ``None``.

    Returns ``(message, http_status)``. Shared by the owner's **two** routes to
    the same decision — the in-app POST and the emailed approve link — so the
    operator's daily cap and the collection's member ceiling mean the same thing
    whichever one they reach for.

    They used not to. The in-app view checked both and the email link approved
    unconditionally, which made `INVITE_EMAILS_PER_DAY` — a cap that exists to
    protect a deployment's sending reputation, not to police the product —
    walkable one recommendation at a time by the owner simply clicking the link
    in their mail client instead of the button in the app. Nothing documented
    the difference, and the in-app path's own reasoning ("an approval that can't
    be delivered should say so rather than half-happen") argues against it.

    The quota is charged to the **owner** on both paths (see
    ``deliver_invitation``), so it is the owner's allowance that is read here —
    never the member's, who cannot send anything on their own.
    """
    collection = proposal.collection
    if _invite_quota_left(collection.owner_id) == 0:
        return _INVITE_QUOTA_MESSAGE, 429
    # Someone already in the group costs the counter nothing, so a full
    # collection must not refuse an approval that would add nobody.
    if (
        collection.capacity_ceiling("invites")
        and not collection.invites.filter(email=proposal.email).exists()
    ):
        full = collection.capacity_violation("invites", adding=1)
        if full:
            return full, 400
    return None


def deliver_invitation(collection, email, inviter_name, quota_user_code=None, proposer_name=None):
    """Create the invitee (if new), mint the RSVP pair and send the invitation.

    Assumes the caller has already checked permission, the daily quota and the
    member ceiling — those produce different HTTP answers per caller, so they
    stay in the views.

    ``quota_user_code`` is whose daily allowance this send is charged to. For an
    approved proposal that is the **owner**, not the member who suggested it: the
    email leaves the owner's group under the deployment's sending domain, and the
    reputation being protected is theirs.

    Returns ``(invited_user, already_invited)``.
    """
    email = email.lower()
    invited_user, created = User.objects.get_or_create(email=email, defaults={"email": email})
    if created:
        Event.log(Event.Kind.USER_JOINED, actor=invited_user)

    if collection.is_invited(invited_user.code):
        return invited_user, True

    # Resend-safe: a fresh pair replaces any pending one for this user+collection.
    RSVP.objects.filter(
        user_code=invited_user,
        target_code=collection.code,
        action__in=[RSVP.Action.COLLECTION_INVITE, RSVP.Action.COLLECTION_REJECT],
    ).delete()
    accept_rsvp = RSVP.objects.create(
        user_code=invited_user,
        user_email=email,
        action=RSVP.Action.COLLECTION_INVITE,
        target_code=collection.code,
    )
    reject_rsvp = RSVP.objects.create(
        user_code=invited_user,
        user_email=email,
        action=RSVP.Action.COLLECTION_REJECT,
        target_code=collection.code,
    )

    send_collection_invite_email(
        inviter_name,
        collection.headline,
        email,
        accept_rsvp.action_link(),
        reject_rsvp.action_link(),
        collection=collection,
        proposer_name=proposer_name,
    )
    if quota_user_code:
        _consume_invite_quota(quota_user_code, 1)
    return invited_user, False


def create_proposal(collection, proposer, email, note=""):
    """Record a member's suggestion and put it in front of the owner.

    **Nothing reaches the proposed address here** — no User row, no email. If the
    owner says no, that person must never learn they were suggested.

    Returns ``(proposal, approve_rsvp, reject_rsvp)``.
    """
    email = email.lower()
    with transaction.atomic():
        proposal = InvitationProposal.objects.create(
            collection=collection, proposer=proposer, email=email, note=note
        )
        # Addressed to the OWNER — they are the one acting on these links.
        approve_rsvp = RSVP.objects.create(
            user_code=collection.owner,
            user_email=collection.owner.email,
            action=RSVP.Action.PROPOSAL_APPROVE,
            target_code=proposal.code,
        )
        reject_rsvp = RSVP.objects.create(
            user_code=collection.owner,
            user_email=collection.owner.email,
            action=RSVP.Action.PROPOSAL_REJECT,
            target_code=proposal.code,
        )
        InAppNotification.objects.create(
            user=collection.owner,
            type=InAppNotification.Type.INVITE_PROPOSED,
            payload={
                "collection_headline": collection.headline,
                "collection_code": collection.code,
                "proposer_name": proposer.display_name,
                "email": email,
                "note": note,
            },
        )

    send_invitation_proposal_email(
        owner_email=collection.owner.email,
        proposer_name=proposer.display_name,
        collection_headline=collection.headline,
        proposed_email=email,
        note=note,
        approve_link=approve_rsvp.action_link(),
        reject_link=reject_rsvp.action_link(),
        collection=collection,
    )
    return proposal, approve_rsvp, reject_rsvp


def approve_proposal(proposal):
    """The owner said yes: send the invitation for real.

    Charged to the owner's quota (see ``deliver_invitation``). Returns
    ``(invited_user, already_invited)``; `already_invited` means somebody else
    got there first while the proposal was waiting, which is a no-op, not an
    error.
    """
    collection = proposal.collection
    invited_user, already = deliver_invitation(
        collection,
        proposal.email,
        collection.owner.display_name,
        quota_user_code=collection.owner_id,
        # The invitee almost certainly knows the member who suggested them, not
        # the owner — without this line a warm recommendation lands as an email
        # from a stranger. Bare `name`, so a proposer who never set one simply
        # doesn't get a line rather than having their address forwarded (L2).
        proposer_name=proposal.proposer.name,
    )
    proposal.status = InvitationProposal.Status.APPROVED
    proposal.resolved = timezone.now()
    proposal.save(update_fields=["status", "resolved"])

    InAppNotification.objects.create(
        user=proposal.proposer,
        type=InAppNotification.Type.INVITE_PROPOSAL_APPROVED,
        payload={
            "collection_headline": collection.headline,
            "collection_code": collection.code,
            "email": proposal.email,
            # Kept for the inbox's back-compatibility branch, which still has to
            # read rows written as INVITE_PROPOSED before this type existed.
            "approved": True,
        },
    )
    return invited_user, already


def reject_proposal(proposal):
    """The owner said no. The proposer is told; the proposed person never is.

    **No reason travels with it.** The owner may be enforcing rules we know
    nothing about — a subscription, papers, a waiting list — and a product that
    demanded a justification would either put words in their mouth or turn a
    quiet no into an argument. The proposer learns the answer and nothing else.
    """
    collection = proposal.collection
    proposal.status = InvitationProposal.Status.REJECTED
    proposal.resolved = timezone.now()
    proposal.save(update_fields=["status", "resolved"])

    InAppNotification.objects.create(
        user=proposal.proposer,
        type=InAppNotification.Type.INVITE_PROPOSAL_DECLINED,
        payload={
            "collection_headline": collection.headline,
            "collection_code": collection.code,
            "owner_name": collection.owner.name,
            "email": proposal.email,
        },
    )
    send_proposal_declined_email(
        proposer_email=proposal.proposer.email,
        owner_name=collection.owner.name,
        collection_headline=collection.headline,
        proposed_email=proposal.email,
        collection=collection,
    )

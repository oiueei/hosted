"""A member proposes, the owner decides, and nobody is contacted before that.

Members could not bring anyone in at all: every new person cost an owner action.
But an owner is not merely a bottleneck to route around — the group may be
closed, may run on subscriptions, papers or rules of admission the product knows
nothing about. So a member suggests and the owner answers, and the guarantee
these tests exist to hold is the ordering: **the proposed address learns nothing
until the owner says yes.**
"""

from unittest.mock import patch

import pytest
from django.core import mail
from django.core.cache import caches
from django.test import override_settings
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from core.models import RSVP, Collection, Event, InvitationProposal, User
from core.models.notification import InAppNotification
from core.services.invitation_service import deliver_invitation

PROPOSE_URL = "/api/v1/collections/{code}/invite/propose/"

# The quota follows RATELIMIT_ENABLE, which the test settings turn off; switch it
# on with a local-memory cache, the same way test_invite_quota.py does.
QUOTA_SETTINGS = {
    "RATELIMIT_ENABLE": True,
    "CACHES": {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "proposal-quota-test",
        }
    },
}


def client_for(user):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    return client


@pytest.fixture
def member(db):
    return User.objects.create(code="MEMB01", email="member@test.com", name="Lele")


@pytest.fixture
def group(db, member):
    owner = User.objects.create(code="OWNR01", email="owner@test.com", name="Lala")
    collection = Collection.objects.create(code="GRP001", owner=owner, headline="The street")
    collection.invites.add(member)
    return collection


@pytest.mark.django_db
class TestProposing:
    def test_a_member_can_suggest_someone_and_nothing_reaches_them(self, group, member):
        """The whole point: the proposal goes to the owner, not to the guest.

        If the owner says no, the person suggested must never learn they were —
        so at this stage there is no email to them and not even a User row.
        """
        mail.outbox.clear()
        resp = client_for(member).post(
            PROPOSE_URL.format(code=group.code),
            {"email": "friend@test.com", "note": "my downstairs neighbour"},
            format="json",
        )

        assert resp.status_code == 200
        proposal = InvitationProposal.objects.get(collection=group)
        assert proposal.email == "friend@test.com"
        assert proposal.status == InvitationProposal.Status.PENDING

        assert not User.objects.filter(email="friend@test.com").exists(), (
            "the proposed person must not exist as an account yet"
        )
        recipients = [addr for m in mail.outbox for addr in m.to]
        assert "friend@test.com" not in recipients, "the proposed person must not be emailed"
        assert group.owner.email in recipients, "the owner is the one who has to decide"

    def test_the_owner_is_told_in_the_app_too_with_the_note(self, group, member):
        """The owner needs the proposer's word to decide — an address alone is
        nothing to go on when the group has rules of admission."""
        client_for(member).post(
            PROPOSE_URL.format(code=group.code),
            {"email": "friend@test.com", "note": "she's paid the subs"},
            format="json",
        )

        note = InAppNotification.objects.get(
            user=group.owner, type=InAppNotification.Type.INVITE_PROPOSED
        )
        assert note.payload["email"] == "friend@test.com"
        assert note.payload["note"] == "she's paid the subs"
        assert note.payload["proposer_name"] == "Lele"

    def test_a_stranger_cannot_propose(self, group, db):
        outsider = User.objects.create(code="OUTS01", email="outsider@test.com")
        resp = client_for(outsider).post(
            PROPOSE_URL.format(code=group.code), {"email": "x@test.com"}, format="json"
        )
        assert resp.status_code == 400
        assert InvitationProposal.objects.count() == 0

    def test_the_owner_can_switch_proposals_off(self, group, member):
        """`allow_member_proposals` is the owner saying they don't want to be
        asked at all — a group with a waiting list or an admission process may
        not want the question raised every week."""
        group.allow_member_proposals = False
        group.save(update_fields=["allow_member_proposals"])

        resp = client_for(member).post(
            PROPOSE_URL.format(code=group.code), {"email": "friend@test.com"}, format="json"
        )

        assert resp.status_code == 403
        assert InvitationProposal.objects.count() == 0

    def test_the_same_person_cannot_be_queued_twice(self, group, member):
        url = PROPOSE_URL.format(code=group.code)
        first = client_for(member).post(url, {"email": "f@test.com"}, format="json")
        assert first.status_code == 200
        second = client_for(member).post(url, {"email": "f@test.com"}, format="json")
        assert second.status_code == 400
        assert InvitationProposal.objects.filter(email="f@test.com").count() == 1

    def test_the_owner_is_sent_to_the_real_invite_instead(self, group):
        """An owner has the actual invitation one endpoint over. Queuing a
        suggestion for themselves to approve would be a round trip to nowhere."""
        resp = client_for(group.owner).post(
            PROPOSE_URL.format(code=group.code), {"email": "friend@test.com"}, format="json"
        )

        assert resp.status_code == 400
        assert "invite them directly" in str(resp.data)
        assert InvitationProposal.objects.count() == 0

    def test_suggesting_somebody_already_in_the_group_is_refused(self, group, member):
        """Answered here rather than by the owner: it needs no decision."""
        resp = client_for(member).post(
            PROPOSE_URL.format(code=group.code), {"email": member.email}, format="json"
        )

        assert resp.status_code == 400
        assert InvitationProposal.objects.count() == 0

    def test_an_address_already_inside_is_answered_exactly_like_one_merely_queued(
        self, group, member
    ):
        """The refusal must not say **which** of the two it was.

        Split, the membership branch was an oracle: a member could put any
        address to this endpoint, 30 a day, and read a yes/no on whether it
        belongs to a co-member. The roster a non-owner receives carries `code`
        and `name` and no email precisely so those addresses stay the owner's to
        see (L2), and this handed the same fact back one guess at a time. So the
        two answers have to be byte-identical — a difference in wording, status
        or shape is the whole vulnerability.
        """
        url = PROPOSE_URL.format(code=group.code)
        client_for(member).post(url, {"email": "queued@test.com"}, format="json")

        inside = client_for(member).post(url, {"email": member.email}, format="json")
        queued = client_for(member).post(url, {"email": "queued@test.com"}, format="json")

        assert inside.status_code == queued.status_code == 400
        assert inside.data == queued.data
        # And a stranger nobody has mentioned still gets a *different* answer —
        # otherwise this test would pass on an endpoint that refused everything.
        fresh = client_for(member).post(url, {"email": "stranger@test.com"}, format="json")
        assert fresh.status_code == 200


@pytest.mark.django_db
class TestDeciding:
    def _propose(self, group, member, email="friend@test.com"):
        client_for(member).post(
            PROPOSE_URL.format(code=group.code), {"email": email}, format="json"
        )
        return InvitationProposal.objects.get(collection=group, email=email)

    def test_approving_sends_the_real_invitation(self, group, member):
        proposal = self._propose(group, member)
        mail.outbox.clear()

        resp = client_for(group.owner).post(f"/api/v1/proposals/{proposal.code}/approve/")

        assert resp.status_code == 200
        proposal.refresh_from_db()
        assert proposal.status == InvitationProposal.Status.APPROVED
        # Indistinguishable from an owner's own invite: same RSVP pair.
        assert RSVP.objects.filter(
            user_email="friend@test.com",
            target_code=group.code,
            action=RSVP.Action.COLLECTION_INVITE,
        ).exists()
        assert "friend@test.com" in [addr for m in mail.outbox for addr in m.to]

    def test_the_invitation_says_who_suggested_them(self, group, member):
        """Lili knows Lele, not Lala.

        Without this line the invitation reads as an email from a stranger, which
        is the difference between a recommendation and a cold approach. The
        invitation is still the owner's — the proposer is context, not authorship.
        """
        proposal = self._propose(group, member)
        mail.outbox.clear()

        client_for(group.owner).post(f"/api/v1/proposals/{proposal.code}/approve/")

        sent = next(m for m in mail.outbox if "friend@test.com" in m.to)
        assert "Lele" in sent.body

    def test_a_nameless_proposer_is_not_outed_by_their_email_address(self, group, member):
        """`display_name` falls back to the email, and this message goes to a
        third party outside the group. A proposer who never set a name must lose
        the line, not have their address forwarded to a stranger (L2)."""
        member.name = ""
        member.save(update_fields=["name"])
        proposal = self._propose(group, member)
        mail.outbox.clear()

        client_for(group.owner).post(f"/api/v1/proposals/{proposal.code}/approve/")

        sent = next(m for m in mail.outbox if "friend@test.com" in m.to)
        assert member.email not in sent.body
        assert member.email not in str(sent.alternatives)

    def test_the_note_is_for_the_owner_only(self, group, member):
        """The proposer's word about somebody is written for the owner's decision.
        It must not travel on to the person it describes."""
        client_for(member).post(
            PROPOSE_URL.format(code=group.code),
            {"email": "friend@test.com", "note": "she can be a bit much but she's sound"},
            format="json",
        )
        proposal = InvitationProposal.objects.get(collection=group)
        mail.outbox.clear()

        client_for(group.owner).post(f"/api/v1/proposals/{proposal.code}/approve/")

        sent = next(m for m in mail.outbox if "friend@test.com" in m.to)
        assert "a bit much" not in sent.body
        assert "a bit much" not in str(sent.alternatives)

    def test_declining_tells_the_proposer_and_never_the_proposed(self, group, member):
        """CA's call: say no clearly, give no reason.

        Silence would leave the member waiting and asking again. A reason would
        either put words in the owner's mouth or turn a quiet no into an
        argument — the group's rules are not the product's business.
        """
        proposal = self._propose(group, member)
        mail.outbox.clear()

        resp = client_for(group.owner).post(f"/api/v1/proposals/{proposal.code}/reject/")

        assert resp.status_code == 200
        proposal.refresh_from_db()
        assert proposal.status == InvitationProposal.Status.REJECTED

        recipients = [addr for m in mail.outbox for addr in m.to]
        assert member.email in recipients, "the proposer is told"
        assert "friend@test.com" not in recipients, "the proposed person is never contacted"
        assert not User.objects.filter(email="friend@test.com").exists()

        note = InAppNotification.objects.get(
            user=member, type=InAppNotification.Type.INVITE_PROPOSAL_DECLINED
        )
        assert "reason" not in note.payload

    def test_the_proposer_cannot_approve_their_own_suggestion(self, group, member):
        """Otherwise the approval is theatre and the owner's gate is not a gate."""
        proposal = self._propose(group, member)

        resp = client_for(member).post(f"/api/v1/proposals/{proposal.code}/approve/")

        assert resp.status_code == 403
        proposal.refresh_from_db()
        assert proposal.status == InvitationProposal.Status.PENDING
        assert not User.objects.filter(email="friend@test.com").exists()

    def test_a_decision_cannot_be_made_twice(self, group, member):
        proposal = self._propose(group, member)
        owner_client = client_for(group.owner)
        assert owner_client.post(f"/api/v1/proposals/{proposal.code}/approve/").status_code == 200
        again = owner_client.post(f"/api/v1/proposals/{proposal.code}/reject/")
        assert again.status_code == 400


@pytest.mark.django_db
class TestTheEmailLinks:
    """The owner's other route: the approve/reject links in the email."""

    def _proposal_rsvps(self, group, member):
        client_for(member).post(
            PROPOSE_URL.format(code=group.code), {"email": "friend@test.com"}, format="json"
        )
        proposal = InvitationProposal.objects.get(collection=group)
        approve = RSVP.objects.get(target_code=proposal.code, action=RSVP.Action.PROPOSAL_APPROVE)
        reject = RSVP.objects.get(target_code=proposal.code, action=RSVP.Action.PROPOSAL_REJECT)
        return proposal, approve, reject

    def test_a_get_only_previews_so_a_link_scanner_cannot_invite_anyone(self, group, member):
        """Approving mails a third party. A mail client prefetching the link must
        not be able to do that on the owner's behalf — the same guard the booking
        decisions use."""
        proposal, approve, _ = self._proposal_rsvps(group, member)
        mail.outbox.clear()

        resp = APIClient().get(f"/api/v1/rsvp/{approve.token}/")

        assert resp.status_code == 200
        assert resp.data["requires_confirmation"] is True
        assert resp.data["email"] == "friend@test.com"
        proposal.refresh_from_db()
        assert proposal.status == InvitationProposal.Status.PENDING
        assert mail.outbox == [], "a bare GET must send nothing"
        assert not User.objects.filter(email="friend@test.com").exists()

    def test_a_post_commits_and_burns_both_links(self, group, member):
        proposal, approve, reject = self._proposal_rsvps(group, member)

        resp = APIClient().post(f"/api/v1/rsvp/{approve.token}/")

        assert resp.status_code == 200
        proposal.refresh_from_db()
        assert proposal.status == InvitationProposal.Status.APPROVED
        # The other link must not still work on a settled decision.
        assert not RSVP.objects.filter(
            target_code=proposal.code,
            action__in=[RSVP.Action.PROPOSAL_APPROVE, RSVP.Action.PROPOSAL_REJECT],
        ).exists()
        assert APIClient().post(f"/api/v1/rsvp/{reject.token}/").status_code == 401

    def test_the_no_link_declines_and_burns_both_too(self, group, member):
        """The other half of the owner's email, and the one that had never been
        exercised: every test above posts the *approve* token.

        Saying no from the mail client must reach exactly the same place as
        saying no in the app — the proposer told, the proposed person never
        contacted, and neither link left alive.
        """
        proposal, approve, reject = self._proposal_rsvps(group, member)
        mail.outbox.clear()

        resp = APIClient().post(f"/api/v1/rsvp/{reject.token}/")

        assert resp.status_code == 200
        proposal.refresh_from_db()
        assert proposal.status == InvitationProposal.Status.REJECTED

        recipients = [addr for m in mail.outbox for addr in m.to]
        assert member.email in recipients, "the proposer is told"
        assert "friend@test.com" not in recipients, "the proposed person is never contacted"
        assert not User.objects.filter(email="friend@test.com").exists()
        assert not RSVP.objects.filter(
            target_code=proposal.code,
            action__in=[RSVP.Action.PROPOSAL_APPROVE, RSVP.Action.PROPOSAL_REJECT],
        ).exists()
        assert APIClient().post(f"/api/v1/rsvp/{approve.token}/").status_code == 401

    def test_a_link_to_a_settled_suggestion_says_so_and_dies(self, group, member):
        """Two links reach one decision, and an owner may have both open — in the
        app and in their mail. The second one to arrive must not re-run it."""
        proposal, approve, reject = self._proposal_rsvps(group, member)
        client_for(group.owner).post(f"/api/v1/proposals/{proposal.code}/reject/")
        # The in-app path burns the pair, so mint a link that outlived its
        # decision the way a forwarded or cached one would.
        stale = RSVP.objects.create(
            user_code=group.owner,
            user_email=group.owner.email,
            action=RSVP.Action.PROPOSAL_APPROVE,
            target_code=proposal.code,
        )
        mail.outbox.clear()

        resp = APIClient().post(f"/api/v1/rsvp/{stale.token}/")

        assert resp.status_code == 400
        assert "no longer pending" in str(resp.data)
        proposal.refresh_from_db()
        assert proposal.status == InvitationProposal.Status.REJECTED
        assert mail.outbox == [], "a settled suggestion must not invite anybody"
        assert not RSVP.objects.filter(code=stale.code).exists(), "the dead link is consumed"


@pytest.mark.django_db
class TestQuota:
    @patch("core.services.invitation_service.send_collection_invite_email")
    def test_an_approved_invitation_is_charged_to_the_owner(self, mock_send, group, member):
        """CA's call, and the right one: the email leaves the owner's group under
        the deployment's sending domain, so it is the owner's daily allowance it
        spends — not the member's, who cannot send anything on their own."""
        client_for(member).post(
            PROPOSE_URL.format(code=group.code), {"email": "friend@test.com"}, format="json"
        )
        proposal = InvitationProposal.objects.get(collection=group)

        with patch("core.services.invitation_service._consume_invite_quota") as consume:
            client_for(group.owner).post(f"/api/v1/proposals/{proposal.code}/approve/")

        consume.assert_called_once_with(group.owner_id, 1)


# ── The two guards on approval, on BOTH of the owner's routes ────────────────
#
# An approval sends an email to a third party and adds a member, so it answers
# to the operator's daily cap and the collection's member ceiling. There are two
# ways for the owner to approve — the in-app button and the emailed link — and
# the link used to apply neither, which made the cap walkable by clicking the
# mail instead of the app. These run every case against both doors.


def _proposal_for(group, member, email="friend@test.com"):
    client_for(member).post(PROPOSE_URL.format(code=group.code), {"email": email}, format="json")
    return InvitationProposal.objects.get(collection=group, email=email)


def _approve_in_app(group, proposal):
    return client_for(group.owner).post(f"/api/v1/proposals/{proposal.code}/approve/")


def _approve_by_email_link(group, proposal):
    rsvp = RSVP.objects.get(target_code=proposal.code, action=RSVP.Action.PROPOSAL_APPROVE)
    return APIClient().post(f"/api/v1/rsvp/{rsvp.token}/")


BOTH_DOORS = [
    pytest.param(_approve_in_app, id="in-app"),
    pytest.param(_approve_by_email_link, id="email-link"),
]


@pytest.mark.django_db
@pytest.mark.parametrize("approve", BOTH_DOORS)
@override_settings(**QUOTA_SETTINGS, INVITE_EMAILS_PER_DAY=1)
def test_an_exhausted_daily_quota_refuses_the_approval(approve, group, member):
    """`INVITE_EMAILS_PER_DAY` guards a deployment's sending reputation, so it
    cannot depend on which of the two doors the owner happens to use.

    The email link used to skip this check entirely: an owner with a mailbox
    full of pending suggestions could approve every one past the cap.
    """
    caches["default"].clear()
    proposal = _proposal_for(group, member)
    # Spend the day's single allowance on an ordinary invite.
    with patch("core.services.invitation_service.send_collection_invite_email"):
        assert (
            client_for(group.owner)
            .post(f"/api/v1/collections/{group.code}/invite/", {"email": "a@test.com"}, "json")
            .status_code
            == 200
        )
    mail.outbox.clear()

    resp = approve(group, proposal)

    assert resp.status_code == 429
    proposal.refresh_from_db()
    assert proposal.status == InvitationProposal.Status.PENDING, (
        "a refused approval decides nothing"
    )
    assert not User.objects.filter(email="friend@test.com").exists()
    assert mail.outbox == [], "nothing may reach the proposed address"


@pytest.mark.django_db
@pytest.mark.parametrize("approve", BOTH_DOORS)
@override_settings(**QUOTA_SETTINGS, INVITE_EMAILS_PER_DAY=1)
def test_a_refused_approval_leaves_the_owner_a_way_back(approve, group, member):
    """ "Not now", not "never": the suggestion and both its links survive, so the
    owner can answer tomorrow instead of asking the member to suggest again."""
    caches["default"].clear()
    proposal = _proposal_for(group, member)
    with patch("core.services.invitation_service.send_collection_invite_email"):
        client_for(group.owner).post(
            f"/api/v1/collections/{group.code}/invite/", {"email": "a@test.com"}, "json"
        )

    assert approve(group, proposal).status_code == 429

    assert RSVP.objects.filter(
        target_code=proposal.code, action=RSVP.Action.PROPOSAL_APPROVE
    ).exists()
    assert RSVP.objects.filter(
        target_code=proposal.code, action=RSVP.Action.PROPOSAL_REJECT
    ).exists()


@pytest.mark.django_db
@pytest.mark.parametrize("approve", BOTH_DOORS)
@override_settings(COLLECTION_INVITES_BLOCK=2)
def test_a_full_collection_refuses_the_approval(approve, group, member):
    """The member ceiling is checked where invitations are *sent*, so approving
    one is exactly where it bites. Both doors, for the same reason as the quota.
    """
    group.invites.add(User.objects.create(email="second@test.com"))
    proposal = _proposal_for(group, member)
    mail.outbox.clear()

    resp = approve(group, proposal)

    assert resp.status_code == 400
    assert "reached its limit" in str(resp.data)
    proposal.refresh_from_db()
    assert proposal.status == InvitationProposal.Status.PENDING
    assert not User.objects.filter(email="friend@test.com").exists()
    assert mail.outbox == []


@pytest.mark.django_db
@pytest.mark.parametrize("approve", BOTH_DOORS)
@override_settings(COLLECTION_INVITES_BLOCK=2)
def test_declining_is_never_blocked_by_a_full_collection(approve, group, member):
    """Saying no adds nobody and sends one email to a member who is already
    inside the count. A ceiling that stopped the owner clearing their queue
    would leave them with a queue they cannot answer."""
    group.invites.add(User.objects.create(email="second@test.com"))
    proposal = _proposal_for(group, member)

    resp = client_for(group.owner).post(f"/api/v1/proposals/{proposal.code}/reject/")

    assert resp.status_code == 200
    proposal.refresh_from_db()
    assert proposal.status == InvitationProposal.Status.REJECTED


@pytest.mark.django_db
class TestApprovedRecommendationIsDistinguishable:
    """A recommendation and an owner's own invite must not blur into one number.

    The whole design of `deliver_invitation` is that an approved proposal is
    *indistinguishable* from an owner's invite — same RSVP pair, same email,
    same quota — so neither code path can rot. That is right for delivery and
    wrong for measurement: without a mark, the feature that lets members grow
    the group is unmeasurable, and there is no way to tell whether it works.
    """

    def test_the_accept_rsvp_carries_the_mark_only_when_a_member_suggested_them(
        self, collection, user
    ):
        deliver_invitation(collection, "direct@test.com", "Owner")
        deliver_invitation(collection, "viafriend@test.com", "Owner", proposer_name="Lele")

        direct = RSVP.objects.get(
            user_email="direct@test.com", action=RSVP.Action.COLLECTION_INVITE
        )
        recommended = RSVP.objects.get(
            user_email="viafriend@test.com", action=RSVP.Action.COLLECTION_INVITE
        )
        assert direct.context == {}
        assert recommended.context == {"via": "recommendation"}

    def test_accepting_each_lands_in_its_own_door(self, client, collection):
        deliver_invitation(collection, "direct@test.com", "Owner")
        deliver_invitation(collection, "viafriend@test.com", "Owner", proposer_name="Lele")

        for email in ("direct@test.com", "viafriend@test.com"):
            rsvp = RSVP.objects.get(user_email=email, action=RSVP.Action.COLLECTION_INVITE)
            assert client.get(f"/api/v1/auth/verify/{rsvp.token}/").status_code == 200

        by_email = {
            User.objects.get(code=e.actor_code).email: e.source
            for e in Event.objects.filter(kind=Event.Kind.MEMBER_JOINED)
        }
        assert by_email["direct@test.com"] == Event.Source.INVITE
        assert by_email["viafriend@test.com"] == Event.Source.RECOMMENDATION

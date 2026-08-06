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
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from core.models import RSVP, Collection, InvitationProposal, User
from core.models.notification import InAppNotification

PROPOSE_URL = "/api/v1/collections/{code}/invite/propose/"


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

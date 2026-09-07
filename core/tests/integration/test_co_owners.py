"""A co-owner gets owner-level admin powers without becoming the CASCADE root.

Promoted from a COMMUNITY collection's own `invites` (never a separate door
in), a co-owner may do everything the owner can except delete the collection
or promote/demote another co-owner — those stay owner-only. These tests pin
the permission surface `is_curator` widened; the promote/demote endpoint
itself is covered separately once it exists.
"""

import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from core.models import Collection, InvitationProposal, User


def client_for(user):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    return client


@pytest.fixture
def owner(db):
    return User.objects.create(code="OWNR01", email="owner@test.com", name="Lala")


@pytest.fixture
def co_owner(db):
    return User.objects.create(code="COOW01", email="coowner@test.com", name="Lele")


@pytest.fixture
def member(db):
    return User.objects.create(code="MEMB01", email="member@test.com", name="Lili")


@pytest.fixture
def stranger(db):
    return User.objects.create(code="STRA01", email="stranger@test.com", name="Lolo")


@pytest.fixture
def group(db, owner, co_owner, member):
    """A COMMUNITY collection with one co-owner already promoted."""
    collection = Collection.objects.create(
        code="GRP001", owner=owner, headline="The street", mode=Collection.Mode.COMMUNITY
    )
    collection.invites.add(co_owner, member)
    collection.co_owners.add(co_owner)
    return collection


class TestACoOwnerHasOwnerLevelPowers:
    def test_a_co_owner_can_edit_the_collection(self, group, co_owner):
        res = client_for(co_owner).patch(
            f"/api/v1/collections/{group.code}/", {"headline": "New name"}, format="json"
        )
        assert res.status_code == 200
        group.refresh_from_db()
        assert group.headline == "New name"

    def test_a_co_owner_can_invite(self, group, co_owner):
        res = client_for(co_owner).post(
            f"/api/v1/collections/{group.code}/invite/",
            {"email": "friend@test.com"},
            format="json",
        )
        assert res.status_code == 200

    def test_a_co_owner_can_revoke_a_member(self, group, co_owner, member):
        res = client_for(co_owner).delete(
            f"/api/v1/collections/{group.code}/invite/",
            {"user_code": member.code},
            format="json",
        )
        assert res.status_code == 200
        assert not group.invites.filter(code=member.code).exists()

    def test_a_co_owner_can_broadcast(self, group, co_owner):
        res = client_for(co_owner).post(
            f"/api/v1/collections/{group.code}/broadcast/",
            {"message": "Bring snacks"},
            format="json",
        )
        assert res.status_code == 200

    def test_a_co_owner_can_manage_the_share_link(self, group, co_owner):
        res = client_for(co_owner).post(f"/api/v1/collections/{group.code}/share-link/")
        assert res.status_code == 200
        assert res.data["share_token"]

    def test_a_co_owner_can_view_stats(self, group, co_owner):
        res = client_for(co_owner).get(f"/api/v1/collections/{group.code}/stats/")
        assert res.status_code == 200

    def test_a_co_owner_can_export_the_collection(self, group, co_owner):
        res = client_for(co_owner).get(f"/api/v1/collections/{group.code}/export/")
        assert res.status_code == 200

    def test_a_co_owner_can_answer_a_members_proposal(self, group, co_owner, member):
        group.allow_member_proposals = True
        group.save(update_fields=["allow_member_proposals"])
        # member proposes someone (member is still invited at this point)
        client_for(member).post(
            f"/api/v1/collections/{group.code}/invite/propose/",
            {"email": "suggested@test.com"},
            format="json",
        )
        proposal = InvitationProposal.objects.get(collection=group, email="suggested@test.com")
        res = client_for(co_owner).post(f"/api/v1/proposals/{proposal.code}/approve/")
        assert res.status_code == 200


class TestACoOwnerIsNotTheOwner:
    def test_a_co_owner_cannot_delete_the_collection(self, group, co_owner):
        res = client_for(co_owner).delete(f"/api/v1/collections/{group.code}/")
        assert res.status_code == 403
        assert Collection.objects.filter(code=group.code).exists()

    def test_a_co_owner_cannot_leave_like_a_plain_member(self, group, co_owner):
        res = client_for(co_owner).post(f"/api/v1/collections/{group.code}/leave/")
        assert res.status_code == 400
        assert group.invites.filter(code=co_owner.code).exists()

    def test_a_co_owner_cannot_propose_to_their_own_group(self, group, co_owner):
        res = client_for(co_owner).post(
            f"/api/v1/collections/{group.code}/invite/propose/",
            {"email": "someone@test.com"},
            format="json",
        )
        assert res.status_code == 400


class TestAPlainMemberOrStrangerHasNoCuratorPower:
    def test_a_plain_member_cannot_invite(self, group, member):
        res = client_for(member).post(
            f"/api/v1/collections/{group.code}/invite/",
            {"email": "friend@test.com"},
            format="json",
        )
        assert res.status_code == 403

    def test_a_stranger_cannot_edit(self, group, stranger):
        res = client_for(stranger).patch(
            f"/api/v1/collections/{group.code}/", {"headline": "Hijack"}, format="json"
        )
        assert res.status_code == 403


class TestRemovingAMemberStripsCoOwnerStatus:
    def test_revoking_a_co_owner_clears_their_co_owner_row_too(self, group, owner, co_owner):
        assert group.co_owners.filter(code=co_owner.code).exists()

        res = client_for(owner).delete(
            f"/api/v1/collections/{group.code}/invite/",
            {"user_code": co_owner.code},
            format="json",
        )

        assert res.status_code == 200
        assert not group.co_owners.filter(code=co_owner.code).exists()
        assert not group.invites.filter(code=co_owner.code).exists()

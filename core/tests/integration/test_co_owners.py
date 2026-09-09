"""A co-curator gets the founder's admin reach without becoming the CASCADE root.

Promoted from the collection's own `invites` (never a separate door in), in
**either** mode (2026-09, co-curators in PROPRIETARY), a co-curator may do
everything the owner can except delete the collection — that alone stays
owner-only. Promoting and demoting another co-curator is curator-wide; the
founding `owner` is an FK, not an `invites` row, so this endpoint structurally
cannot demote them. These tests pin the permission surface `is_curator`
widened, and the promote/demote endpoint (`CollectionCoOwnerView`) itself.
"""

import pytest
from django.test import override_settings
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from core.models import Collection, InvitationProposal, User
from core.models.notification import InAppNotification

CO_OWNERS_URL = "/api/v1/collections/{code}/co-owners/"
CO_OWNERS_DISABLED = "core.tests.sample_creator_policy.CoOwnersDisabledCreatorPolicy"


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


class TestPromotingACoOwner:
    def test_the_owner_promotes_a_member(self, group, owner, member):
        assert not group.co_owners.filter(code=member.code).exists()

        res = client_for(owner).post(
            CO_OWNERS_URL.format(code=group.code), {"user_code": member.code}, format="json"
        )

        assert res.status_code == 200
        assert group.co_owners.filter(code=member.code).exists()
        assert group.invites.filter(code=member.code).exists()

    def test_promoting_notifies_the_member_once_even_if_repeated(self, group, owner, member):
        url = CO_OWNERS_URL.format(code=group.code)
        client_for(owner).post(url, {"user_code": member.code}, format="json")
        client_for(owner).post(url, {"user_code": member.code}, format="json")

        assert (
            InAppNotification.objects.filter(
                user=member, type=InAppNotification.Type.PROMOTED_CO_OWNER
            ).count()
            == 1
        )

    def test_a_co_curator_can_promote_another_member(self, group, co_owner, member):
        # Curator-wide since 2026-09: a co-curator has the founder's reach over
        # everything except deleting the collection, appointing help included.
        res = client_for(co_owner).post(
            CO_OWNERS_URL.format(code=group.code), {"user_code": member.code}, format="json"
        )
        assert res.status_code == 200
        assert group.co_owners.filter(code=member.code).exists()

    def test_a_stranger_cannot_promote(self, group, stranger, member):
        res = client_for(stranger).post(
            CO_OWNERS_URL.format(code=group.code), {"user_code": member.code}, format="json"
        )
        assert res.status_code == 403

    def test_a_non_member_cannot_be_promoted(self, group, owner, stranger):
        res = client_for(owner).post(
            CO_OWNERS_URL.format(code=group.code), {"user_code": stranger.code}, format="json"
        )
        assert res.status_code == 400
        assert not group.co_owners.filter(code=stranger.code).exists()

    def test_a_proprietary_collection_allows_promotion(self, db, owner, member):
        # The early adopter's case: a space run PROPRIETARY needs the founder
        # plus one or two co-curators. Mode is not a factor any more.
        proprietary = Collection.objects.create(
            code="PROP01", owner=owner, headline="Solo", mode=Collection.Mode.PROPRIETARY
        )
        proprietary.invites.add(member)

        res = client_for(owner).post(
            CO_OWNERS_URL.format(code=proprietary.code), {"user_code": member.code}, format="json"
        )

        assert res.status_code == 200
        assert proprietary.co_owners.filter(code=member.code).exists()

    def test_a_co_curator_of_a_proprietary_collection_can_promote_another(self, db, owner, member):
        proprietary = Collection.objects.create(
            code="PROP02", owner=owner, headline="Space", mode=Collection.Mode.PROPRIETARY
        )
        second = User.objects.create(code="SECND1", email="second@test.com", name="Nil")
        proprietary.invites.add(member, second)
        proprietary.co_owners.add(member)

        res = client_for(member).post(
            CO_OWNERS_URL.format(code=proprietary.code), {"user_code": second.code}, format="json"
        )

        assert res.status_code == 200
        assert proprietary.co_owners.filter(code=second.code).exists()

    def test_a_deployment_can_withhold_co_owners(self, group, owner, member):
        with override_settings(CREATOR_POLICY=CO_OWNERS_DISABLED):
            res = client_for(owner).post(
                CO_OWNERS_URL.format(code=group.code), {"user_code": member.code}, format="json"
            )

        assert res.status_code == 403
        assert not group.co_owners.filter(code=member.code).exists()


class TestDemotingACoOwner:
    def test_demoting_a_stranger_who_was_never_a_member_is_refused(self, group, owner, stranger):
        res = client_for(owner).delete(
            CO_OWNERS_URL.format(code=group.code), {"user_code": stranger.code}, format="json"
        )
        assert res.status_code == 400

    def test_the_owner_demotes_a_co_owner(self, group, owner, co_owner):
        res = client_for(owner).delete(
            CO_OWNERS_URL.format(code=group.code), {"user_code": co_owner.code}, format="json"
        )

        assert res.status_code == 200
        assert not group.co_owners.filter(code=co_owner.code).exists()
        # Demoted, not removed — still a plain member.
        assert group.invites.filter(code=co_owner.code).exists()

    def test_demoting_notifies_the_co_owner(self, group, owner, co_owner):
        client_for(owner).delete(
            CO_OWNERS_URL.format(code=group.code), {"user_code": co_owner.code}, format="json"
        )

        assert InAppNotification.objects.filter(
            user=co_owner, type=InAppNotification.Type.DEMOTED_CO_OWNER
        ).exists()

    def test_demoting_a_plain_member_is_a_harmless_no_op(self, group, owner, member):
        res = client_for(owner).delete(
            CO_OWNERS_URL.format(code=group.code), {"user_code": member.code}, format="json"
        )

        assert res.status_code == 200
        assert not InAppNotification.objects.filter(
            user=member, type=InAppNotification.Type.DEMOTED_CO_OWNER
        ).exists()

    def test_a_co_curator_can_demote_another_co_curator(self, group, co_owner, member):
        # Curator-wide, and the accepted trade-off: co-curators can ping-pong
        # demotions, with the founder as the circuit breaker (next test).
        group.co_owners.add(member)
        res = client_for(co_owner).delete(
            CO_OWNERS_URL.format(code=group.code), {"user_code": member.code}, format="json"
        )
        assert res.status_code == 200
        assert not group.co_owners.filter(code=member.code).exists()
        assert group.invites.filter(code=member.code).exists()

    def test_the_founding_owner_cannot_be_demoted(self, group, co_owner, owner):
        # The owner is an FK, never an `invites` row, so `_get_target` cannot
        # resolve them — the endpoint structurally cannot touch the founder.
        res = client_for(co_owner).delete(
            CO_OWNERS_URL.format(code=group.code), {"user_code": owner.code}, format="json"
        )
        assert res.status_code == 400
        group.refresh_from_db()
        assert group.owner_id == owner.code
        assert group.is_curator(owner.code)

    def test_demoting_still_works_even_if_the_deployment_has_since_disabled_co_owners(
        self, group, owner, co_owner
    ):
        """Grandfathering: withholding the capability withholds *promoting*,
        never demoting an owner already has standing to reverse."""
        with override_settings(CREATOR_POLICY=CO_OWNERS_DISABLED):
            res = client_for(owner).delete(
                CO_OWNERS_URL.format(code=group.code), {"user_code": co_owner.code}, format="json"
            )

        assert res.status_code == 200
        assert not group.co_owners.filter(code=co_owner.code).exists()

    def test_demoting_still_works_on_a_collection_switched_away_from_community(
        self, db, owner, co_owner
    ):
        """A co-owner's status is sticky across a mode switch — the owner must
        still be able to clean it up rather than being stuck with it."""
        legacy = Collection.objects.create(
            code="LEGACY", owner=owner, headline="Was a group", mode=Collection.Mode.PROPRIETARY
        )
        legacy.invites.add(co_owner)
        legacy.co_owners.add(co_owner)  # sticky from before the mode switch

        res = client_for(owner).delete(
            CO_OWNERS_URL.format(code=legacy.code), {"user_code": co_owner.code}, format="json"
        )

        assert res.status_code == 200
        assert not legacy.co_owners.filter(code=co_owner.code).exists()

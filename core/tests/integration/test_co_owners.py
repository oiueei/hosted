"""A co-curator gets the founder's admin reach without becoming the CASCADE root.

Promoted from the collection's own `invites` (never a separate door in), in
**either** mode (2026-09, co-curators in PROPRIETARY), a co-curator may do
everything the owner can except delete the collection — that alone stays
owner-only. Promoting and demoting another co-curator is curator-wide; the
founding `owner` is an FK, not an `invites` row, so this endpoint structurally
cannot demote them. These tests pin the permission surface `is_curator`
widened, and the promote/demote endpoint (`CollectionCoOwnerView`) itself.
"""

import csv
import json

import pytest
from django.core import mail
from django.core.cache import caches
from django.test import override_settings
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from core.models import RSVP, Collection, InvitationProposal, User
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
        mail.outbox.clear()
        res = client_for(co_owner).post(
            f"/api/v1/collections/{group.code}/invite/",
            {"email": "friend@test.com"},
            format="json",
        )
        assert res.status_code == 200
        # The invitation actually went out — a pending RSVP the invitee can act
        # on, and the email carrying it. 200 alone said only "the endpoint let
        # the co-owner in", not "a stranger was invited".
        assert RSVP.objects.filter(
            user_email="friend@test.com",
            target_code=group.code,
            action=RSVP.Action.COLLECTION_INVITE,
        ).exists()
        assert [m.to[0] for m in mail.outbox] == ["friend@test.com"]
        assert "The street" in mail.outbox[0].body

    def test_a_co_owner_can_revoke_a_member(self, group, co_owner, member):
        res = client_for(co_owner).delete(
            f"/api/v1/collections/{group.code}/invite/",
            {"user_code": member.code},
            format="json",
        )
        assert res.status_code == 200
        assert not group.invites.filter(code=member.code).exists()

    def test_a_co_owner_can_broadcast(self, group, co_owner, member):
        mail.outbox.clear()
        res = client_for(co_owner).post(
            f"/api/v1/collections/{group.code}/broadcast/",
            {"message": "Bring snacks"},
            format="json",
        )
        assert res.status_code == 200
        # The message actually reached the members, and it is the co-owner's
        # address a reply lands on — the one screen where a member learns an
        # address the API otherwise never serves. 200 alone proved neither.
        member_mail = next(m for m in mail.outbox if member.email in m.to)
        assert "Bring snacks" in member_mail.body
        assert member_mail.reply_to == [co_owner.email]
        assert InAppNotification.objects.filter(
            user=member, type=InAppNotification.Type.BROADCAST
        ).exists()

    def test_a_co_owner_can_manage_the_share_link(self, group, co_owner):
        res = client_for(co_owner).post(f"/api/v1/collections/{group.code}/share-link/")
        assert res.status_code == 200
        assert res.data["share_token"]

    def test_a_co_owner_can_view_stats(self, group, co_owner):
        res = client_for(co_owner).get(f"/api/v1/collections/{group.code}/stats/")
        assert res.status_code == 200
        # It is the stats CSV, not just a 200: the co-owner gets the same
        # member-count metric the founder would.
        assert f"{group.code}-stats.csv" in res["Content-Disposition"]
        rows = {r[0]: r[1] for r in csv.reader(res.content.decode().splitlines()) if len(r) >= 2}
        assert rows["Members"] == "2"  # co_owner + member

    def test_a_co_owner_can_export_the_collection(self, group, co_owner, member):
        res = client_for(co_owner).get(f"/api/v1/collections/{group.code}/export/")
        assert res.status_code == 200
        # The whole point of this file: it carries the operational copy of the
        # group, member emails included — the thing the page warns a curator
        # they are about to have on their laptop. A bare 200 proved none of it.
        assert f'filename="oiueei-{group.code}-' in res["Content-Disposition"]
        payload = json.loads(res.content.decode())
        assert payload["_manifest"]["collection_code"] == group.code
        member_emails = {m["email"] for m in payload["members"]}
        assert {co_owner.email, member.email} <= member_emails

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
        mail.outbox.clear()

        res = client_for(co_owner).post(f"/api/v1/proposals/{proposal.code}/approve/")
        assert res.status_code == 200
        # Approving does the real work: the proposal is settled and the actual
        # invitation goes out (an RSVP the suggested person can act on, and the
        # email carrying it). Until now the co-owner reached suggested@ only
        # because nobody checked whether anything happened after the 200.
        proposal.refresh_from_db()
        assert proposal.status == InvitationProposal.Status.APPROVED
        assert RSVP.objects.filter(
            user_email="suggested@test.com",
            target_code=group.code,
            action=RSVP.Action.COLLECTION_INVITE,
        ).exists()
        assert [m.to[0] for m in mail.outbox] == ["suggested@test.com"]


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

    @pytest.fixture
    def capped(self, db, owner):
        """A collection already holding `MAX_CO_OWNERS` co-curators, plus one
        more plain member a further promotion would have to fit."""
        collection = Collection.objects.create(
            code="GRPFUL", owner=owner, headline="Full house", mode=Collection.Mode.PROPRIETARY
        )
        for i in range(Collection.MAX_CO_OWNERS):
            co_curator = User.objects.create(
                code=f"COOF{i:02d}", email=f"full{i}@test.com", name=f"F{i}"
            )
            collection.invites.add(co_curator)
            collection.co_owners.add(co_curator)
        outsider = User.objects.create(code="OUTS01", email="outsider@test.com", name="Lulu")
        collection.invites.add(outsider)
        return collection

    def test_promotion_at_the_cap_refuses_a_new_co_curator(self, capped, owner):
        """With no bound on the set, one stolen curator credential could
        promote the whole roster — and every promotion hands over the member
        list with its emails. At `MAX_CO_OWNERS` a new promotion is a 400 and
        the set stands exactly as it was."""
        outsider = capped.invites.get(code="OUTS01")
        res = client_for(owner).post(
            CO_OWNERS_URL.format(code=capped.code), {"user_code": outsider.code}, format="json"
        )
        assert res.status_code == 400
        assert capped.co_owners.count() == Collection.MAX_CO_OWNERS
        assert not capped.co_owners.filter(code=outsider.code).exists()

    def test_the_cap_refusal_is_coded_so_the_spa_can_say_it_in_the_readers_language(
        self, capped, owner
    ):
        """`core` has no gettext catalogue, so the sentence is English; the code
        and its number are what let the SPA say it in Catalan or Spanish (the same
        shape a request's refusals carry), with the sentence as the fallback."""
        outsider = capped.invites.get(code="OUTS01")
        res = client_for(owner).post(
            CO_OWNERS_URL.format(code=capped.code), {"user_code": outsider.code}, format="json"
        )
        assert res.status_code == 400
        assert res.data["code"] == "co_owners_full"
        assert res.data["params"] == {"max": Collection.MAX_CO_OWNERS}
        assert "maximum of" in res.data["error"]

    def test_repromoting_an_existing_co_curator_at_the_cap_stays_idempotent(self, capped, owner):
        # The `already` path must never hit the ceiling: promoting someone who
        # is already a co-curator grows nothing, so it keeps answering 200.
        existing = capped.co_owners.first()
        res = client_for(owner).post(
            CO_OWNERS_URL.format(code=capped.code), {"user_code": existing.code}, format="json"
        )
        assert res.status_code == 200
        assert capped.co_owners.count() == Collection.MAX_CO_OWNERS

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

    def test_a_demoted_co_owner_loses_the_curator_reach(self, group, owner, co_owner):
        # The M2M row going is half the story; the half that matters is that the
        # endpoints stop obeying them. Before this, nothing asked a demoted
        # co-owner for a curator action and checked it was refused.
        edit_url = f"/api/v1/collections/{group.code}/"
        before = client_for(co_owner).patch(edit_url, {"headline": "Still mine"}, format="json")
        assert before.status_code == 200

        client_for(owner).delete(
            CO_OWNERS_URL.format(code=group.code), {"user_code": co_owner.code}, format="json"
        )

        after = client_for(co_owner).patch(edit_url, {"headline": "Hijack"}, format="json")
        assert after.status_code == 403
        group.refresh_from_db()
        assert group.headline == "Still mine"
        # ...and stats, another curator-gated endpoint, is refused too.
        assert (
            client_for(co_owner).get(f"/api/v1/collections/{group.code}/stats/").status_code == 403
        )

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


class TestPromotingAndDemotingHaveAnHourlyCeiling:
    """The ceiling on who can thrash the co-curator set: a compromised curator
    credential must not be able to promote and demote without bound, each demotion
    firing a notice. django-ratelimit counts `post` and `delete` in separate
    groups, so each verb has its own thirty."""

    @override_settings(
        RATELIMIT_ENABLE=True,
        CACHES={
            "default": {
                "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
                "LOCATION": "co-owner-ceiling-ratelimit-test",
            }
        },
    )
    @pytest.mark.parametrize("verb", ["post", "delete"])
    def test_a_curator_may_promote_or_demote_thirty_times_an_hour_and_no_more(
        self, verb, group, owner, co_owner, member
    ):
        """Thirty calls in the hour all go through; the thirty-first is a 429 and
        changes nothing. The thirty are calls that change nothing but still count
        (demoting a plain member, re-promoting a co-curator — both a 200), so the
        thirty-first can be aimed at someone the call *would* have changed and
        the test can see it did not."""
        caches["default"].clear()
        client = client_for(owner)
        url = CO_OWNERS_URL.format(code=group.code)
        call = getattr(client, verb)
        if verb == "delete":
            idle, target = member, co_owner
        else:
            idle, target = co_owner, member

        statuses = [
            call(url, {"user_code": idle.code}, format="json").status_code for _ in range(30)
        ]
        assert statuses == [200] * 30

        rejected = call(url, {"user_code": target.code}, format="json")

        assert rejected.status_code == 429
        if verb == "delete":
            # The co-curator it targeted keeps the role and the membership.
            assert group.co_owners.filter(code=co_owner.code).exists()
            assert group.invites.filter(code=co_owner.code).exists()
            notice = InAppNotification.Type.DEMOTED_CO_OWNER
        else:
            # The member it targeted stays a plain member.
            assert not group.co_owners.filter(code=member.code).exists()
            notice = InAppNotification.Type.PROMOTED_CO_OWNER
        assert not InAppNotification.objects.filter(user=target, type=notice).exists()

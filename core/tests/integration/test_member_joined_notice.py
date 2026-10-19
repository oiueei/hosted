"""Whoever runs a group is told, in the app, when someone joins it.

Joining is never blocked or approved, in any mode and through any door. The team
(founder and co-curators) hears of each sign-up instead. Every door ends in
``_join_collection``, so what is pinned here is that each of them raises the
notice, that only a *new* member does, and who receives it.
"""

import pytest
from rest_framework.test import APIClient

from core.models import RSVP, Collection, User
from core.models.notification import InAppNotification

Type = InAppNotification.Type


def _joined(collection=None):
    notices = InAppNotification.objects.filter(type=Type.MEMBER_JOINED)
    if collection is not None:
        notices = notices.filter(payload__collection_code=collection.code)
    return notices


@pytest.fixture
def founder(db):
    return User.objects.create(code="FOUND1", email="lala@your-domain.test", name="Lala")


@pytest.fixture
def co_curator(db):
    return User.objects.create(code="COCUR1", email="lele@your-domain.test", name="Lele")


@pytest.fixture
def member(db):
    return User.objects.create(code="MEMB01", email="lili@your-domain.test", name="Lili")


@pytest.fixture
def newcomer(db):
    return User.objects.create(code="NEWC01", email="lolo@your-domain.test", name="Lolo")


@pytest.fixture
def group(founder, co_curator, member):
    collection = Collection.objects.create(
        code="GRP001",
        owner=founder,
        headline="The street",
        visibility=Collection.Visibility.PUBLIC,
        share_token="tok_member_joined_0123",
    )
    collection.invites.add(co_curator, member)
    collection.co_owners.add(co_curator)
    return collection


def _client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _by_public_group(group, newcomer):
    return _client(newcomer).post(f"/api/v1/collections/{group.code}/join/")


def _by_share_link(group, newcomer):
    return _client(newcomer).post(f"/api/v1/share/{group.share_token}/join/")


def _by_invitation(group, newcomer):
    accept = RSVP.objects.create(
        user_code=newcomer,
        user_email=newcomer.email,
        action=RSVP.Action.COLLECTION_INVITE,
        target_code=group.code,
    )
    return APIClient().get(f"/api/v1/rsvp/{accept.token}/")


def _by_magic_link_join(group, newcomer):
    APIClient().post(
        "/api/v1/auth/join/",
        {"email": newcomer.email, "collection_code": group.code},
        format="json",
    )
    link = RSVP.objects.get(user_code=newcomer, action=RSVP.Action.MAGIC_LINK)
    return APIClient().get(f"/api/v1/rsvp/{link.token}/")


DOORS = [_by_public_group, _by_share_link, _by_invitation, _by_magic_link_join]


@pytest.mark.django_db
class TestTheTeamIsTold:
    @pytest.mark.parametrize("door", DOORS, ids=lambda d: d.__name__)
    def test_every_door_tells_the_founder_and_each_co_curator(
        self, door, group, newcomer, founder, co_curator
    ):
        resp = door(group, newcomer)

        assert resp.status_code == 200
        assert set(_joined(group).values_list("user_id", flat=True)) == {
            founder.code,
            co_curator.code,
        }
        notice = _joined(group).get(user=founder)
        assert notice.payload == {
            "collection_code": group.code,
            "collection_headline": "The street",
            "member_name": "Lolo",
        }

    def test_the_one_joining_and_the_members_are_told_nothing(self, group, newcomer, member):
        _by_public_group(group, newcomer)

        recipients = set(_joined(group).values_list("user_id", flat=True))
        assert newcomer.code not in recipients
        assert member.code not in recipients

    def test_a_curator_who_joins_is_not_told_of_themselves(self, group, founder, co_curator):
        # A co-curator is always in `invites` already, so the only curator who can be
        # "new" is one added to the team through the funnel directly.
        from core.views.auth import _join_collection

        extra = User.objects.create(code="EXTRA1", email="lulu@your-domain.test", name="Lulu")
        group.co_owners.add(extra)

        _join_collection(group, extra, source="")

        recipients = set(_joined(group).values_list("user_id", flat=True))
        assert extra.code not in recipients
        assert recipients == {founder.code, co_curator.code}

    def test_joining_again_does_not_tell_twice(self, group, newcomer):
        _by_public_group(group, newcomer)
        _by_share_link(group, newcomer)
        _by_public_group(group, newcomer)

        assert _joined(group).filter(user=group.owner).count() == 1

    def test_a_member_with_no_name_travels_as_an_empty_name_never_an_address(self, group, newcomer):
        newcomer.name = ""
        newcomer.save(update_fields=["name"])

        _by_public_group(group, newcomer)

        payload = _joined(group).get(user=group.owner).payload
        assert payload["member_name"] == ""
        assert newcomer.email not in str(payload)

    def test_it_only_informs(self):
        assert Type.MEMBER_JOINED not in InAppNotification.ACTION_NOTICE_TYPES

"""Whoever stops running a collection loses its team's notices, and nothing else.

After a co-curator was demoted, that person's inbox still
read "New request — Lolioctupus asked for…": a notice they had received as a
manager, asking for a decision the server would now refuse. A demotion and a
removal from the group both end the role, so both take out of that person's inbox
the request and reservation notices **of that collection** (the ones that go to
whoever manages: ``InAppNotification.team_booking_notices``).

What must stay is as much the point: the notices that are theirs as a person (their
own requests and their answers, the group's messages, the ``DEMOTED_CO_OWNER`` that
says what happened), those of **another** collection they still run, the other
managers' own, and the notices about a thing they still run themselves (a
COMMUNITY member who contributed it, or one they curate through another group).
"""

import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from core.models import Collection, Thing, User
from core.models.notification import InAppNotification

pytestmark = pytest.mark.django_db

Type = InAppNotification.Type


def client_for(user):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    return client


@pytest.fixture
def lala(db):
    return User.objects.create(code="LALA01", email="lala@test.com", name="Lala")


@pytest.fixture
def lele(db):
    return User.objects.create(code="LELE01", email="lele@test.com", name="Lele")


@pytest.fixture
def lili(db):
    return User.objects.create(code="LILI01", email="lili@test.com", name="Lili")


def _group(code, owner, mode, *people, co_curators=()):
    group = Collection.objects.create(code=code, owner=owner, headline=code, mode=mode)
    group.invites.add(*people)
    group.co_owners.add(*co_curators)
    return group


@pytest.fixture
def world(lala, lele, lili):
    """Two PROPRIETARY groups Lele co-curates, and a COMMUNITY one where he does too
    and has contributed a thing of his own."""
    prop = Collection.Mode.PROPRIETARY
    tools = _group("TOOLS1", lala, prop, lele, lili, co_curators=[lele])
    books = _group("BOOKS1", lala, prop, lele, lili, co_curators=[lele])
    street = _group("STREET", lala, Collection.Mode.COMMUNITY, lele, lili, co_curators=[lele])

    def thing(code, owner, *groups):
        t = Thing.objects.create(
            code=code, type=Thing.Type.GIFT_THING, owner=owner, headline=f"Thing {code}"
        )
        for g in groups:
            g.things.add(t)
        return t

    return {
        "tools": tools,
        "books": books,
        "street": street,
        "drill": thing("DRILL1", lala, tools),
        "novel": thing("NOVEL1", lala, books),
        # In both PROPRIETARY groups: Lele curates it through either.
        "both": thing("BOTH01", lala, tools, books),
        # Lele's own, in the COMMUNITY group he co-curates.
        "his": thing("HIS001", lele, street),
    }


def _ask(who, thing, group):
    res = client_for(who).post(
        f"/api/v1/things/{thing.code}/request/", {"collection_code": group.code}, format="json"
    )
    assert res.status_code == 201, res.data


def _inbox(user):
    """(type, thing_code or collection_code) of everything in the inbox, sorted."""
    return sorted(
        (n.type, n.payload.get("thing_code") or n.payload.get("collection_code") or "")
        for n in InAppNotification.objects.filter(user=user)
    )


def _demote(by, group, who):
    res = client_for(by).delete(
        f"/api/v1/collections/{group.code}/co-owners/", {"user_code": who.code}, format="json"
    )
    assert res.status_code == 200, res.data


def _remove_from_group(by, group, who):
    res = client_for(by).delete(
        f"/api/v1/collections/{group.code}/invite/", {"user_code": who.code}, format="json"
    )
    assert res.status_code == 200, res.data


@pytest.fixture
def lele_inbox_before(world, lala, lele, lili):
    """Lele's inbox as a curator of three groups, built by the real flows: a request
    in each PROPRIETARY group, one for the thing he owns in the COMMUNITY group, one
    for the thing that sits in both, his own request answered, and a group message."""
    _ask(lili, world["drill"], world["tools"])
    _ask(lili, world["novel"], world["books"])
    _ask(lili, world["both"], world["tools"])
    _ask(lili, world["his"], world["street"])
    # Lele asks for something himself, and Lala says yes: a notice that is his as a
    # person (the requester's own answer), in the group he is about to lose.
    asked = Thing.objects.create(
        code="ASKED1", type=Thing.Type.GIFT_THING, owner=lala, headline="Thing ASKED1"
    )
    world["tools"].things.add(asked)
    _ask(lele, asked, world["tools"])
    from core.models import BookingPeriod

    booking = BookingPeriod.objects.get(thing_code=asked, requester_code=lele)
    assert client_for(lala).post(f"/api/v1/bookings/{booking.code}/accept/").status_code == 200
    InAppNotification.objects.create(
        user=lele,
        type=Type.BROADCAST,
        payload={"collection_code": "TOOLS1", "message": "Hello", "owner_name": "Lala"},
    )
    return _inbox(lele)


class TestADemotedCoCuratorLosesThatGroupsTeamNotices:
    def test_the_requests_of_that_group_go_and_everything_else_stays(
        self, world, lala, lele, lele_inbox_before
    ):
        before = lele_inbox_before
        # The starting point: a request for each thing, his own answered request, the
        # group message — so what follows is a deletion, not an absence.
        assert before.count((Type.BOOKING_REQUESTED, "DRILL1")) == 1
        assert (Type.BOOKING_REQUESTED, "NOVEL1") in before
        assert (Type.BOOKING_ACCEPTED, "ASKED1") in before

        _demote(lala, world["tools"], lele)

        after = _inbox(lele)
        # Gone: the request for the drill, which only TOOLS1 sent him.
        assert (Type.BOOKING_REQUESTED, "DRILL1") not in after
        # Kept, as theirs: the request of another group he still co-curates, the thing
        # that sits in both groups (he still curates BOOKS1), the thing he owns himself,
        # his own request's answer, the group message — and the notice that tells him
        # what happened, created by the demotion itself.
        assert (Type.BOOKING_REQUESTED, "NOVEL1") in after
        assert (Type.BOOKING_REQUESTED, "BOTH01") in after
        assert (Type.BOOKING_REQUESTED, "HIS001") in after
        assert (Type.BOOKING_ACCEPTED, "ASKED1") in after
        assert (Type.BROADCAST, "TOOLS1") in after
        assert (Type.DEMOTED_CO_OWNER, "TOOLS1") in after
        # Nothing else went: exactly the drill's request, plus the demotion notice.
        assert sorted(after) == sorted(
            [n for n in before if n != (Type.BOOKING_REQUESTED, "DRILL1")]
            + [(Type.DEMOTED_CO_OWNER, "TOOLS1")]
        )

    def test_every_kind_of_team_notice_of_that_group_goes(self, world, lala, lele):
        for kind in (Type.BOOKING_REQUESTED, Type.BOOKING_DECIDED, Type.RESERVATION_MADE):
            InAppNotification.objects.create(
                user=lele,
                type=kind,
                payload={"thing_code": "DRILL1", "collection_code": "TOOLS1"},
            )

        _demote(lala, world["tools"], lele)

        assert _inbox(lele) == [(Type.DEMOTED_CO_OWNER, "TOOLS1")]

    def test_the_other_managers_keep_theirs(self, world, lala, lele, lili):
        _ask(lili, world["drill"], world["tools"])
        founders = _inbox(lala)
        assert founders == [(Type.BOOKING_REQUESTED, "DRILL1")]

        _demote(lala, world["tools"], lele)

        # Lala's request is hers: it asks her for a decision she can still make.
        assert _inbox(lala) == founders

    def test_a_notice_of_another_group_they_still_run_is_not_touched_even_for_a_vanished_thing(
        self, world, lala, lele
    ):
        # The scope is the collection, not only the thing: this request was sent by
        # BOOKS1, which he still co-curates, about a thing that has since left it, so
        # he can no longer decide it either way. It is not this demotion's to remove.
        Thing.objects.create(code="GONE01", type=Thing.Type.GIFT_THING, owner=lala, headline="x")
        InAppNotification.objects.create(
            user=lele,
            type=Type.BOOKING_REQUESTED,
            payload={"thing_code": "GONE01", "collection_code": "BOOKS1"},
        )

        _demote(lala, world["tools"], lele)

        assert (Type.BOOKING_REQUESTED, "GONE01") in _inbox(lele)

    def test_a_thing_they_own_in_a_community_group_stays_theirs_to_decide(
        self, world, lala, lele, lili
    ):
        _ask(lili, world["his"], world["street"])
        assert _inbox(lele) == [(Type.BOOKING_REQUESTED, "HIS001")]

        _demote(lala, world["street"], lele)

        # Demoted from the group's staff, but it is his thing: the request about it
        # still asks for something he can do.
        assert (Type.BOOKING_REQUESTED, "HIS001") in _inbox(lele)

    def test_a_thing_in_two_groups_stays_while_they_curate_the_other(self, world, lala, lele, lili):
        _ask(lili, world["both"], world["tools"])

        _demote(lala, world["tools"], lele)

        assert (Type.BOOKING_REQUESTED, "BOTH01") in _inbox(lele)

    def test_a_thing_in_two_groups_goes_once_they_curate_neither(self, world, lala, lele, lili):
        _ask(lili, world["both"], world["tools"])

        _demote(lala, world["books"], lele)  # BOOKS1 first: still curates TOOLS1
        assert (Type.BOOKING_REQUESTED, "BOTH01") in _inbox(lele)
        _demote(lala, world["tools"], lele)

        assert (Type.BOOKING_REQUESTED, "BOTH01") not in _inbox(lele)


class TestRemovingACoCuratorFromTheGroupDoesTheSame:
    def test_the_requests_of_that_group_go_the_other_groups_stay(
        self, world, lala, lele, lele_inbox_before
    ):
        _remove_from_group(lala, world["tools"], lele)

        after = _inbox(lele)
        assert (Type.BOOKING_REQUESTED, "DRILL1") not in after
        assert (Type.BOOKING_REQUESTED, "NOVEL1") in after
        assert (Type.BOOKING_REQUESTED, "BOTH01") in after  # BOOKS1 still his
        assert (Type.BOOKING_REQUESTED, "HIS001") in after
        assert (Type.BOOKING_ACCEPTED, "ASKED1") in after

    def test_a_plain_member_removed_loses_nothing_they_were_never_sent_as_staff(
        self, world, lala, lili
    ):
        # Lili is no co-curator: whatever she holds is hers. (A COMMUNITY member's
        # request notice for her own thing is a team notice by shape, and removing
        # her from the group is not what ends it.)
        InAppNotification.objects.create(
            user=lili,
            type=Type.BOOKING_REQUESTED,
            payload={"thing_code": "HIS001", "collection_code": "STREET"},
        )

        _remove_from_group(lala, world["street"], lili)

        # Told she was removed (that is its own notice), and the request is still there.
        assert (Type.BOOKING_REQUESTED, "HIS001") in _inbox(lili)

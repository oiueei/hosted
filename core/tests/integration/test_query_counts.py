"""Query-count regression guards for list endpoints.

These lock in the prefetch/annotation work so a future change can't silently
reintroduce a per-thing query (N+1) on transfer_count / my_pending_booking /
the nested-things serialisation.
"""

import json
from datetime import date, timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from core.models import RSVP, Collection
from core.models.transfer import ThingTransfer
from core.tests.factories import (
    BookingPeriodFactory,
    CollectionFactory,
    RSVPFactory,
    ThingFactory,
    ThingTransferFactory,
    UserFactory,
)


def _make_things(owner, collection, n):
    collection.things.add(*ThingFactory.create_batch(n, owner=owner))


def _warm_activity(client):
    """Prime DailyActivityMiddleware's once-per-user/day write + cache guard.

    The middleware writes a DailyActivity row on a user's first authenticated
    request of the day and only reads cache thereafter. Without this warm-up the
    first measured request below would alone carry that INSERT, so the equality
    guards would be comparing first-visit bookkeeping instead of serialisation
    cost. One throwaway request makes both measured requests steady-state.
    """
    client.get("/api/v1/auth/me/")


@pytest.mark.django_db
class TestListEndpointQueryBudgets:
    """The query count of a list/detail response must be CONSTANT in the number
    of things it serialises — adding more things must add zero queries."""

    def test_collection_detail_has_no_per_thing_queries(
        self, authenticated_client, user, collection
    ):
        url = f"/api/v1/collections/{collection.code}/"
        _warm_activity(authenticated_client)
        _make_things(user, collection, 2)
        with CaptureQueriesContext(connection) as small:
            r1 = authenticated_client.get(url)
        assert r1.status_code == 200

        _make_things(user, collection, 4)
        with CaptureQueriesContext(connection) as big:
            r2 = authenticated_client.get(url)
        assert r2.status_code == 200
        assert len(r2.data["things"]) == 6

        assert len(big) == len(small), (
            f"N+1 on collection detail: {len(small)} queries for 2 things, {len(big)} for 6"
        )

    def test_anon_collection_detail_reuses_things_prefetch(self, api_client, user):
        """Non-owner viewers (including anonymous ones) take the Python-side
        INACTIVE filter in get_things(). A regression to .exclude() there
        discards the collection's Prefetch("things", ...) cache — it doesn't
        scale with N, but it does re-fire the things query plus its 4 nested
        prefetches (faq_set/deal/2x bookings), doubling 7 queries to 12."""
        coll = CollectionFactory(owner=user, visibility=Collection.Visibility.PUBLIC)
        _make_things(user, coll, 2)
        with CaptureQueriesContext(connection) as small:
            r1 = api_client.get(f"/api/v1/collections/{coll.code}/")
        assert r1.status_code == 200

        _make_things(user, coll, 4)
        with CaptureQueriesContext(connection) as big:
            r2 = api_client.get(f"/api/v1/collections/{coll.code}/")
        assert r2.status_code == 200
        assert len(r2.data["things"]) == 6

        assert len(big) == len(small), (
            f"N+1 on anon collection detail: {len(small)} queries for 2 things, {len(big)} for 6"
        )
        assert len(small) == 7, (
            f"expected the collection's things Prefetch to be reused (7 queries), "
            f"got {len(small)} — an .exclude() on obj.things would discard it"
        )

    def test_things_list_has_no_per_thing_queries(self, authenticated_client, user, collection):
        url = "/api/v1/things/"
        _warm_activity(authenticated_client)
        _make_things(user, collection, 2)
        with CaptureQueriesContext(connection) as small:
            r1 = authenticated_client.get(url)
        assert r1.status_code == 200

        _make_things(user, collection, 4)
        with CaptureQueriesContext(connection) as big:
            r2 = authenticated_client.get(url)
        assert r2.status_code == 200

        assert len(big) == len(small), f"N+1 on things list: {len(small)} queries vs {len(big)}"

    def test_transfer_count_annotation_is_correct(
        self, authenticated_client, user, user2, collection
    ):
        """The _transfer_count annotation (Count distinct) reports the true
        per-thing transfer count through the endpoint."""
        thing = ThingFactory(owner=user, type="LEND_THING")
        collection.things.add(thing)
        ThingTransferFactory(thing=thing, from_user=user, to_user=user2, lent_date=date.today())
        ThingTransferFactory(thing=thing, from_user=user2, to_user=user, lent_date=date.today())

        r = authenticated_client.get(f"/api/v1/collections/{collection.code}/")
        assert r.status_code == 200
        thing_data = next(t for t in r.data["things"] if t["code"] == thing.code)
        assert thing_data["transfer_count"] == 2
        assert ThingTransfer.objects.filter(thing=thing).count() == 2


@pytest.mark.django_db
class TestNPlusOneGuards:
    """Endpoints whose query count must NOT grow with the number of rows they
    serialise. Each guard fails if its prefetch/annotation/memoisation regresses."""

    def test_owner_calendar_constant_with_requesters(self, authenticated_client, user, collection):
        """The owner calendar must select_related the requester (its name is read
        per period) so more bookings don't add per-period queries."""
        thing = ThingFactory(owner=user, type="LEND_THING")
        collection.things.add(thing)

        def make(n, offset):
            for i in range(n):
                BookingPeriodFactory(
                    thing_code=thing,
                    requester_code=UserFactory(),
                    thing_type="LEND_THING",
                    start_date=date(2026, 1, 1) + timedelta(days=(offset + i) * 10),
                    end_date=date(2026, 1, 5) + timedelta(days=(offset + i) * 10),
                    status="PENDING",
                )

        url = f"/api/v1/things/{thing.code}/calendar/"
        _warm_activity(authenticated_client)
        make(2, 0)
        with CaptureQueriesContext(connection) as small:
            r1 = authenticated_client.get(url)
        assert r1.status_code == 200

        make(2, 2)
        with CaptureQueriesContext(connection) as big:
            r2 = authenticated_client.get(url)
        assert r2.status_code == 200
        assert len(big) == len(small), (
            f"N+1 on owner calendar requesters: {len(small)} vs {len(big)}"
        )

    def test_collection_detail_embeds_owner_bookings_for_free(
        self, authenticated_client, user, collection
    ):
        """Serving the owner's bookings on the card must add no query, per thing
        or per booking.

        The card used to GET /things/{code}/calendar/ once each, so an owner
        opening a 30-item lending library fired 30 requests. Those rows were
        already in memory (`_blocked_periods`), so the field is free — but only
        while the prefetch keeps `select_related("requester_code")`: the
        serialiser prints the requester's name, and dropping that join trades one
        request per card for one query per booking, which is worse.
        """
        url = f"/api/v1/collections/{collection.code}/"
        _warm_activity(authenticated_client)

        def lend_thing_with_bookings(n, offset):
            thing = ThingFactory(owner=user, type="LEND_THING")
            collection.things.add(thing)
            for i in range(n):
                BookingPeriodFactory(
                    thing_code=thing,
                    requester_code=UserFactory(),
                    thing_type="LEND_THING",
                    start_date=date(2099, 1, 1) + timedelta(days=(offset + i) * 10),
                    end_date=date(2099, 1, 5) + timedelta(days=(offset + i) * 10),
                    status="PENDING",
                )

        lend_thing_with_bookings(2, 0)
        with CaptureQueriesContext(connection) as small:
            r1 = authenticated_client.get(url)
        assert r1.status_code == 200
        assert any(t["bookings"] for t in r1.data["things"]), (
            "the owner must actually receive the embedded bookings"
        )

        # Two more things, each with its own bookings and its own requesters.
        lend_thing_with_bookings(2, 2)
        lend_thing_with_bookings(2, 4)
        with CaptureQueriesContext(connection) as big:
            r2 = authenticated_client.get(url)
        assert r2.status_code == 200

        assert len(big) == len(small), (
            f"N+1 on embedded owner bookings: {len(small)} queries for 1 thing, "
            f"{len(big)} for 3 (each with 2 bookings and distinct requesters)"
        )

    def test_collection_detail_hides_bookings_from_non_owners(self, api_client, user):
        """A card's booking list names the people who requested it — owner only.

        The field rides on the same serialiser an anonymous visitor gets for a
        PUBLIC collection, so the gate is the only thing between a requester's
        name and the open web.
        """
        public = CollectionFactory(owner=user, visibility=Collection.Visibility.PUBLIC)
        thing = ThingFactory(owner=user, type="LEND_THING")
        public.things.add(thing)
        BookingPeriodFactory(
            thing_code=thing,
            requester_code=UserFactory(name="Nosy Neighbour"),
            thing_type="LEND_THING",
            start_date=date(2099, 2, 1),
            end_date=date(2099, 2, 5),
            status="PENDING",
        )

        resp = api_client.get(f"/api/v1/collections/{public.code}/")

        assert resp.status_code == 200
        assert resp.data["things"][0]["bookings"] is None
        assert "Nosy Neighbour" not in str(resp.data)

    def test_collection_list_constant_with_pending_invites(self, authenticated_client, user):
        """The collection list must batch pending_invites (one RSVP query for the
        whole page), not query the RSVP table once per owned collection."""

        def make(n):
            for _ in range(n):
                coll = CollectionFactory(owner=user)
                RSVPFactory(
                    user_code=UserFactory(),
                    action=RSVP.Action.COLLECTION_INVITE,
                    target_code=coll.code,
                )

        _warm_activity(authenticated_client)
        make(2)
        with CaptureQueriesContext(connection) as small:
            r1 = authenticated_client.get("/api/v1/collections/")
        assert r1.status_code == 200

        make(2)
        with CaptureQueriesContext(connection) as big:
            r2 = authenticated_client.get("/api/v1/collections/")
        assert r2.status_code == 200
        assert len(big) == len(small), (
            f"N+1 on collection-list pending_invites: {len(small)} vs {len(big)}"
        )


@pytest.mark.django_db
class TestDataExportQueryBudgets:
    """An export walks every table a person appears in, so an N+1 here is not a
    slow page — it is a 30-second Heroku timeout on the one request somebody
    makes when they are already unhappy enough to be leaving."""

    def test_account_export_is_constant_in_what_it_carries(self, authenticated_client, user):
        def grow():
            coll = CollectionFactory(owner=user)
            _make_things(user, coll, 3)
            coll.invites.add(UserFactory(), UserFactory())
            RSVPFactory(
                user_code=UserFactory(),
                action=RSVP.Action.COLLECTION_INVITE,
                target_code=coll.code,
            )
            for thing in ThingFactory.create_batch(2, owner=user):
                BookingPeriodFactory(thing_code=thing)
                ThingTransferFactory(thing=thing, from_user=user)

        _warm_activity(authenticated_client)
        grow()
        with CaptureQueriesContext(connection) as small:
            r1 = authenticated_client.get("/api/v1/auth/export/")
        assert r1.status_code == 200

        for _ in range(3):
            grow()
        with CaptureQueriesContext(connection) as big:
            r2 = authenticated_client.get("/api/v1/auth/export/")
        assert r2.status_code == 200
        assert len(big) == len(small), (
            f"N+1 in the account export: {len(small)} queries for one group, {len(big)} for four"
        )

    def test_collection_export_is_constant_in_the_size_of_the_group(
        self, authenticated_client, user
    ):
        coll = CollectionFactory(owner=user)
        url = f"/api/v1/collections/{coll.code}/export/"
        _warm_activity(authenticated_client)
        _make_things(user, coll, 5)
        coll.invites.add(*UserFactory.create_batch(3))
        with CaptureQueriesContext(connection) as small:
            r1 = authenticated_client.get(url)
        assert r1.status_code == 200

        _make_things(user, coll, 195)
        coll.invites.add(*UserFactory.create_batch(20))
        with CaptureQueriesContext(connection) as big:
            r2 = authenticated_client.get(url)
        assert r2.status_code == 200
        assert len(json.loads(r2.content)["things"]) == 200
        assert len(big) == len(small), (
            f"N+1 in the collection export: {len(small)} queries for 5 things, {len(big)} for 200"
        )

    def test_a_two_hundred_thing_group_is_still_a_file_and_not_a_disk(
        self, authenticated_client, user
    ):
        """The other half of the budget, which query counts can't see.

        `assertNumQueries` catches the N+1; it says nothing about the megabytes
        assembled in memory before the response is written. Photos travel as
        URLs precisely so this stays bounded — the day somebody
        inlines an image as base64 "for convenience", this is what notices.
        """
        coll = CollectionFactory(owner=user)
        _make_things(user, coll, 200)

        res = authenticated_client.get(f"/api/v1/collections/{coll.code}/export/")

        assert res.status_code == 200
        assert len(res.content) < 1_000_000, f"200 things weighed {len(res.content)} bytes"

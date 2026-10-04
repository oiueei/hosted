"""`collection_menu` on the thing endpoint (X4, CA 2026-10-04).

The page of a thing read from inside a collection paints the same corner menu as
the collection's own page, and needs a little of that collection to do it: whether
the viewer curates it or belongs to it, its welcome document, how often it sends a
summary and whether the viewer has muted it, and — for a curator — whether it holds
anything bookable by date (the calendar download). It does **not** get the
collection itself: `GET /collections/{code}/` carries every one of its things.

So the thing serializer answers it, from the collection it already resolves for the
`collection_*` fields, and only to the two kinds of reader the menu is for. These
tests pin who gets it, what it holds, that a listing and an unframed read never pay
for it, and what it costs.
"""

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from core.models import Collection
from core.tests.factories import ThingFactory, UserFactory
from core.utils import doc_asset_url

DOC = "oiueei/documents/welcome-doc-1"


def _client(user):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    return client


def _read(client, thing, through=None):
    url = f"/api/v1/things/{thing.code}/"
    if through is not None:
        url += f"?collection={through}"
    response = client.get(url)
    assert response.status_code == 200
    return response.data


@pytest.fixture
def group(db, user, collection, thing):
    """The founder's collection, with its one thing, in PROPRIETARY mode."""
    return collection


@pytest.fixture
def member(db, group):
    person = UserFactory()
    group.invites.add(person)
    return person


@pytest.fixture
def co_curator(db, group):
    person = UserFactory()
    group.invites.add(person)
    group.co_owners.add(person)
    return person


@pytest.mark.django_db
class TestWhoGetsTheMenu:
    def test_a_member_does(self, group, thing, member):
        menu = _read(_client(member), thing, group.code)["collection_menu"]

        assert menu["is_member"] is True
        assert menu["is_curator"] is False

    def test_the_founder_is_a_curator(self, group, thing, user):
        menu = _read(_client(user), thing, group.code)["collection_menu"]

        assert menu["is_curator"] is True
        assert menu["is_member"] is False

    def test_a_co_curator_is_a_curator_and_not_a_member(self, group, thing, co_curator):
        """As in `CollectionSerializer`: staff is not a rank-and-file member, though a
        co-owner is always in `invites` too."""
        menu = _read(_client(co_curator), thing, group.code)["collection_menu"]

        assert menu["is_curator"] is True
        assert menu["is_member"] is False

    def test_a_signed_in_reader_outside_a_public_group_gets_none(self, user, thing):
        """A public group is readable by anyone: reading is not belonging, and the
        menu's contents (the welcome document above all) are served to the two kinds
        of reader it is for."""
        public = Collection.objects.create(
            code="PUBGRP",
            owner=user,
            headline="Open",
            visibility=Collection.Visibility.PUBLIC,
            welcome_doc=DOC,
        )
        public.things.add(thing)

        data = _read(_client(UserFactory()), thing, public.code)

        assert data["collection_menu"] is None
        assert DOC not in str(data)

    def test_an_anonymous_reader_gets_none(self, user, thing):
        public = Collection.objects.create(
            code="PUBGRP",
            owner=user,
            headline="Open",
            visibility=Collection.Visibility.PUBLIC,
            welcome_doc=DOC,
        )
        public.things.add(thing)

        data = _read(APIClient(), thing, public.code)

        assert data["collection_menu"] is None
        assert DOC not in str(data)

    def test_a_read_that_names_no_collection_gets_none(self, group, thing, member, user):
        """The standalone `/things/:code` page has no collection to speak for."""
        assert _read(_client(member), thing)["collection_menu"] is None
        assert _read(_client(user), thing)["collection_menu"] is None

    def test_naming_a_collection_the_thing_is_not_in_gets_none(self, group, thing, user):
        elsewhere = Collection.objects.create(code="ELSEWH", owner=user, headline="Elsewhere")

        assert _read(_client(user), thing, elsewhere.code)["collection_menu"] is None

    def test_a_member_of_another_collection_only_gets_none(self, group, thing, user):
        """Belonging to *a* collection is not belonging to the one asked for."""
        other = Collection.objects.create(code="OTHERG", owner=user, headline="Other")
        stranger = UserFactory()
        other.invites.add(stranger)
        public = Collection.objects.create(
            code="PUBGRP",
            owner=user,
            headline="Open",
            visibility=Collection.Visibility.PUBLIC,
        )
        public.things.add(thing)

        assert _read(_client(stranger), thing, public.code)["collection_menu"] is None

    def test_a_listing_carries_none_and_so_pays_nothing(self, group, thing, user):
        """Only a thing read through a collection carries it: the SPA's lists never
        send `?collection=`."""
        response = _client(user).get("/api/v1/things/")

        assert response.status_code == 200
        assert [row["collection_menu"] for row in response.data["results"]] == [None]


@pytest.mark.django_db
class TestWhatItHolds:
    def test_a_members_payload(self, group, thing, member):
        menu = _read(_client(member), thing, group.code)["collection_menu"]

        assert menu == {
            "is_curator": False,
            "is_member": True,
            "welcome_doc_url": None,
            "digest_frequency": group.digest_frequency,
            "is_digest_muted": False,
            "has_date_things": False,
        }

    def test_the_welcome_document_goes_to_both_kinds_of_reader(self, group, thing, member, user):
        group.welcome_doc = DOC
        group.save(update_fields=["welcome_doc"])

        for reader in (member, user):
            menu = _read(_client(reader), thing, group.code)["collection_menu"]
            assert menu["welcome_doc_url"] == doc_asset_url(DOC)

    def test_a_member_who_muted_the_summary_reads_it_back(self, group, thing, member):
        group.digest_frequency = Collection.DigestFrequency.WEEKLY
        group.save(update_fields=["digest_frequency"])
        group.digest_muted.add(member)

        menu = _read(_client(member), thing, group.code)["collection_menu"]

        assert menu["digest_frequency"] == "WEEKLY"
        assert menu["is_digest_muted"] is True

    def test_muting_is_the_viewers_own_not_another_members(self, group, thing, member):
        group.digest_frequency = Collection.DigestFrequency.WEEKLY
        group.save(update_fields=["digest_frequency"])
        other = UserFactory()
        group.invites.add(other)
        group.digest_muted.add(other)

        assert (
            _read(_client(member), thing, group.code)["collection_menu"]["is_digest_muted"] is False
        )

    def test_a_group_that_sends_no_summary_reports_nothing_muted(self, group, thing, member):
        group.digest_frequency = Collection.DigestFrequency.NONE
        group.save(update_fields=["digest_frequency"])
        group.digest_muted.add(member)

        menu = _read(_client(member), thing, group.code)["collection_menu"]

        assert menu["digest_frequency"] == "NONE"
        assert menu["is_digest_muted"] is False

    def test_a_curator_is_never_reported_as_having_muted(self, group, thing, user):
        group.digest_frequency = Collection.DigestFrequency.WEEKLY
        group.save(update_fields=["digest_frequency"])
        group.digest_muted.add(user)

        assert (
            _read(_client(user), thing, group.code)["collection_menu"]["is_digest_muted"] is False
        )


@pytest.mark.django_db
class TestTheCalendarEntry:
    """`has_date_things` is the rule the collection page uses: the allowlist when the
    owner set one, else whether the group holds a thing booked by date. A curator's
    only: a member has no calendar."""

    def _menu(self, reader, thing, group):
        return _read(_client(reader), thing, group.code)["collection_menu"]

    def test_an_allowlist_naming_a_date_type_says_yes(self, group, thing, user):
        group.allowed_thing_types = ["GIFT_THING", "LEND_THING"]
        group.save(update_fields=["allowed_thing_types"])

        assert self._menu(user, thing, group)["has_date_things"] is True

    def test_an_allowlist_with_no_date_type_says_no_even_if_a_loan_is_there(
        self, group, thing, user
    ):
        group.allowed_thing_types = ["GIFT_THING"]
        group.save(update_fields=["allowed_thing_types"])
        group.things.add(ThingFactory(owner=user, type="LEND_THING"))

        assert self._menu(user, thing, group)["has_date_things"] is False

    def test_without_an_allowlist_a_date_thing_in_the_group_says_yes(self, group, thing, user):
        assert group.allowed_thing_types == []
        group.things.add(ThingFactory(owner=user, type="RENT_THING"))

        assert self._menu(user, thing, group)["has_date_things"] is True

    def test_without_an_allowlist_and_nothing_by_date_it_says_no(self, group, thing, user):
        assert self._menu(user, thing, group)["has_date_things"] is False

    def test_a_member_never_gets_a_calendar(self, group, thing, member, user):
        group.allowed_thing_types = ["LEND_THING"]
        group.save(update_fields=["allowed_thing_types"])

        assert self._menu(member, thing, group)["has_date_things"] is False


@pytest.mark.django_db
class TestWhatItCosts:
    """The thing endpoint answers a bare row, not the list's prefetched queryset, so
    each lookup here is a query of its own. The budget is small, fixed, and does not
    grow with the group: the collection's things are never loaded for it."""

    def _count(self, reader, thing, through):
        client = _client(reader)
        client.get("/api/v1/auth/me/")  # steady state: DailyActivity's first write
        with CaptureQueriesContext(connection) as queries:
            assert (
                client.get(f"/api/v1/things/{thing.code}/?collection={through}").status_code == 200
            )
        return len(queries)

    def _count_unframed(self, reader, thing):
        client = _client(reader)
        client.get("/api/v1/auth/me/")
        with CaptureQueriesContext(connection) as queries:
            assert client.get(f"/api/v1/things/{thing.code}/").status_code == 200
        return len(queries)

    def test_a_member_pays_for_one_extra_query_at_most(self, group, thing, member):
        group.digest_frequency = Collection.DigestFrequency.WEEKLY
        group.save(update_fields=["digest_frequency"])

        framed = self._count(member, thing, group.code)
        unframed = self._count_unframed(member, thing)

        # The summary switch's state, one query. Whether the member runs the
        # collection is the question `can_manage` already asks (and now shares).
        assert framed - unframed <= 1, f"{unframed} queries unframed, {framed} framed"

    def test_a_member_of_a_community_group_pays_for_two(self, group, thing, member):
        """`can_manage` only asks who curates a PROPRIETARY collection, so here the
        menu is the first to ask about the co-owners: that, and the summary's state."""
        group.mode = Collection.Mode.COMMUNITY
        group.digest_frequency = Collection.DigestFrequency.WEEKLY
        group.save(update_fields=["mode", "digest_frequency"])

        framed = self._count(member, thing, group.code)
        unframed = self._count_unframed(member, thing)

        assert framed - unframed <= 2, f"{unframed} queries unframed, {framed} framed"

    def test_a_group_with_no_summary_costs_nothing_for_a_member(self, group, thing, member):
        group.digest_frequency = Collection.DigestFrequency.NONE
        group.save(update_fields=["digest_frequency"])

        assert self._count(member, thing, group.code) == self._count_unframed(member, thing)

    def test_a_curator_of_an_old_collection_pays_for_the_calendar_question_only(
        self, group, thing, user
    ):
        assert group.allowed_thing_types == []

        framed = self._count(user, thing, group.code)
        unframed = self._count_unframed(user, thing)

        assert framed - unframed <= 1, f"{unframed} queries unframed, {framed} framed"

    def test_it_does_not_grow_with_the_things_in_the_group(self, group, thing, member, user):
        group.digest_frequency = Collection.DigestFrequency.WEEKLY
        group.save(update_fields=["digest_frequency"])
        small_member = self._count(member, thing, group.code)
        small_curator = self._count(user, thing, group.code)

        group.things.add(*ThingFactory.create_batch(8, owner=user))

        assert self._count(member, thing, group.code) == small_member
        assert self._count(user, thing, group.code) == small_curator

    def test_the_curator_check_is_asked_once_for_can_manage_and_the_menu(
        self, group, thing, co_curator
    ):
        """`can_manage` and `collection_menu` need the same answer for the same
        collection; the second reads it from the context instead of asking the
        database about the co-owners again."""
        client = _client(co_curator)
        client.get("/api/v1/auth/me/")
        with CaptureQueriesContext(connection) as queries:
            assert (
                client.get(f"/api/v1/things/{thing.code}/?collection={group.code}").status_code
                == 200
            )

        co_owner_reads = [q for q in queries if "collection_co_owners" in q["sql"]]
        assert len(co_owner_reads) == 1, [q["sql"] for q in co_owner_reads]

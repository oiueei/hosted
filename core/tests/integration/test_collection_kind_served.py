"""Everything that hands the app a ``collection_code`` to navigate to hands it the kind too.

The app's address for a collection is ``/{kind}/{code}``, so a notice, a booking, a
thing, a landing or a share answer that names a collection without its kind would
send the app through a redirect on every click. Nothing is stored for it: the
inbox adds the kind when it serves a notice, so rows written before kinds existed
link properly too.
"""

from datetime import date, timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework import status
from rest_framework.test import APIClient

from core.models import RSVP, BookingPeriod, Collection, Thing
from core.models.notification import InAppNotification

INBOX = "/api/v1/inbox/"


def _group(owner, kind, code, **fields):
    return Collection.objects.create(code=code, owner=owner, headline=code, kind=kind, **fields)


def _notice(user, collection_code=None, type_="BOOKING_REQUESTED"):
    payload = {"thing_headline": "Drill"}
    if collection_code:
        payload["collection_code"] = collection_code
    return InAppNotification.objects.create(user=user, type=type_, payload=payload)


@pytest.mark.django_db
class TestOnAThing:
    def test_a_thing_names_the_kind_of_the_collection_it_is_read_through(
        self, authenticated_client, user
    ):
        library = _group(user, "LIBRARY", "LIBRY1", visibility=Collection.Visibility.PUBLIC)
        thing = Thing.objects.create(
            code="THG001", owner=user, headline="Ladder", type="LEND_THING"
        )
        library.things.add(thing)

        res = authenticated_client.get(f"/api/v1/things/{thing.code}/")

        assert res.data["collection_code"] == "LIBRY1"
        assert res.data["collection_kind"] == "LIBRARY"

    def test_it_says_which_verbs_that_collection_takes(self, authenticated_client, user):
        """A COMMUNITY group whose members may not set a price lists only the free verb,
        and the form that edits a thing has no price field there."""
        free_only = _group(
            user,
            "STALL",
            "STLFRE",
            visibility=Collection.Visibility.PUBLIC,
            mode=Collection.Mode.COMMUNITY,
            allowed_thing_types=["GIFT_THING"],
        )
        thing = Thing.objects.create(code="THG010", owner=user, headline="Vase")
        free_only.things.add(thing)

        res = authenticated_client.get(f"/api/v1/things/{thing.code}/")

        assert res.data["collection_allowed_thing_types"] == ["GIFT_THING"]

    def test_a_thing_in_no_collection_has_none(self, authenticated_client, user):
        thing = Thing.objects.create(code="THG002", owner=user, headline="Loose")

        res = authenticated_client.get(f"/api/v1/things/{thing.code}/")

        assert res.data["collection_kind"] is None
        assert res.data["collection_allowed_thing_types"] == []

    def test_a_private_collection_is_not_named_to_someone_outside_it(
        self, authenticated_client2, user
    ):
        """The kind follows ``collection_code``: both are withheld together."""
        private = _group(user, "SHED", "SHD001", visibility=Collection.Visibility.PRIVATE)
        thing = Thing.objects.create(code="THG003", owner=user, headline="Lamp")
        private.things.add(thing)

        res = authenticated_client2.get(f"/api/v1/things/{thing.code}/")

        assert res.status_code in (status.HTTP_200_OK, status.HTTP_403_FORBIDDEN)
        assert "SHED" not in str(res.data)


@pytest.mark.django_db
class TestOnABooking:
    def test_owner_bookings_say_which_kind_the_request_belongs_to(
        self, authenticated_client, user, user2
    ):
        library = _group(user, "LIBRARY", "LIBRY2")
        thing = Thing.objects.create(code="THG004", owner=user, headline="Saw", type="LEND_THING")
        library.things.add(thing)
        BookingPeriod.objects.create(
            thing_code=thing,
            requester_code=user2,
            requester_email=user2.email,
            owner_code=user,
            start_date=date.today(),
            end_date=date.today() + timedelta(days=2),
        )

        res = authenticated_client.get("/api/v1/owner-bookings/")

        row = res.data["results"][0]
        assert (row["collection_code"], row["collection_kind"]) == ("LIBRY2", "LIBRARY")


@pytest.mark.django_db
class TestInbox:
    def test_a_notice_is_served_with_the_kind_of_its_collection(self, authenticated_client, user):
        _group(user, "SHED", "SHD002")
        _notice(user, "SHD002")

        res = authenticated_client.get(INBOX)

        assert res.data[0]["payload"]["collection_kind"] == "SHED"

    def test_nothing_is_stored_in_the_payload(self, authenticated_client, user):
        _group(user, "SHED", "SHD003")
        notice = _notice(user, "SHD003")

        authenticated_client.get(INBOX)

        notice.refresh_from_db()
        assert "collection_kind" not in notice.payload

    def test_a_notice_with_no_collection_or_a_gone_one_is_served_as_it_is(
        self, authenticated_client, user
    ):
        _notice(user)
        _notice(user, "GONE01")

        res = authenticated_client.get(INBOX)

        for row in res.data:
            assert "collection_kind" not in row["payload"]

    def test_many_notices_from_many_collections_cost_one_extra_query(
        self, authenticated_client, user
    ):
        def queries():
            with CaptureQueriesContext(connection) as ctx:
                assert authenticated_client.get(INBOX).status_code == status.HTTP_200_OK
            return len(ctx)

        queries()  # the first call also pays for what the session caches
        baseline = queries()
        _group(user, "STALL", "STL002")
        _notice(user, "STL002")
        one = queries()
        for n, kind in enumerate(("LIBRARY", "SHED", "STALL", "LIBRARY", "SHED")):
            code = f"CLX00{n}"
            _group(user, kind, code)
            for _ in range(4):
                _notice(user, code)
        many = queries()

        assert one == baseline + 1
        assert many == one, "24 notices from 6 collections must cost what 1 from 1 does"


@pytest.mark.django_db
class TestLandings:
    def test_a_join_link_lands_with_the_collections_kind(self, user, user2):
        library = _group(user, "LIBRARY", "LIBRY3")
        rsvp = RSVP.objects.create(
            user_code=user2,
            user_email=user2.email,
            action=RSVP.Action.COLLECTION_INVITE,
            target_code=library.code,
        )

        res = APIClient().get(f"/api/v1/auth/verify/{rsvp.token}/")

        assert res.data["collection"] == "LIBRY3"
        assert res.data["collection_kind"] == "LIBRARY"

    def test_a_magic_link_that_carries_a_collection_names_its_kind(self, user, user2):
        shed = _group(user, "SHED", "SHD004", visibility=Collection.Visibility.PUBLIC)
        rsvp = RSVP.objects.create(
            user_code=user2,
            user_email=user2.email,
            action=RSVP.Action.MAGIC_LINK,
            origin=RSVP.Origin.POPIN,
            target_code=shed.code,
            context={"join_source": "PUBLIC"},
        )

        res = APIClient().get(f"/api/v1/auth/verify/{rsvp.token}/")

        assert res.data["landing"] == "collection"
        assert res.data["collection_kind"] == "SHED"

    def test_a_login_with_one_group_lands_on_it_with_its_kind(self, user, user2):
        library = _group(user, "LIBRARY", "LIBRY4")
        library.invites.add(user2)
        rsvp = RSVP.objects.create(
            user_code=user2,
            user_email=user2.email,
            action=RSVP.Action.MAGIC_LINK,
            origin=RSVP.Origin.LOGIN,
        )

        res = APIClient().get(f"/api/v1/auth/verify/{rsvp.token}/")

        assert (res.data["collection"], res.data["collection_kind"]) == ("LIBRY4", "LIBRARY")

    def test_a_login_that_lands_on_home_names_no_kind(self, user2):
        rsvp = RSVP.objects.create(
            user_code=user2,
            user_email=user2.email,
            action=RSVP.Action.MAGIC_LINK,
            origin=RSVP.Origin.LOGIN,
        )

        res = APIClient().get(f"/api/v1/auth/verify/{rsvp.token}/")

        assert res.data["landing"] == "home"
        assert "collection_kind" not in res.data


@pytest.mark.django_db
class TestShare:
    TOKEN = "tok_kind_group_0123456"

    def test_joining_by_share_names_the_kind_to_navigate_to(self, authenticated_client2, user):
        _group(user, "LIBRARY", "LIBRY5", share_token=self.TOKEN)

        res = authenticated_client2.post(f"/api/v1/share/{self.TOKEN}/join/")

        assert res.data == {"collection": "LIBRY5", "collection_kind": "LIBRARY", "joined": True}

    def test_the_owner_trying_their_own_link_gets_it_too(self, authenticated_client, user):
        _group(user, "SHED", "SHD005", share_token=self.TOKEN)

        res = authenticated_client.post(f"/api/v1/share/{self.TOKEN}/join/")

        assert res.data["collection_kind"] == "SHED"
        assert res.data["joined"] is False

    def test_the_preview_says_what_kind_of_group_the_link_opens(self, user):
        _group(user, "LIBRARY", "LIBRY6", share_token=self.TOKEN)

        res = APIClient().get(f"/api/v1/share/{self.TOKEN}/preview/")

        assert res.data["kind"] == "LIBRARY"

"""POST /api/v1/collections/{code}/calendar-export/ — the calendar CSV download.

Behaviours guarded here:

- only a curator (owner or co-owner) can pull the file; a plain member and a
  stranger both get 403;
- it is **POST-only** — a bare GET (a mail scanner, a prefetch) gets 405 and
  changes nothing, the same anti-prefetch contract as the digest unsubscribe;
- the response is a CSV attachment named ``{code}-calendar.csv``, tagged
  ``no-store`` (it carries member names) and carrying the new-event count;
- the second POST of the day returns nothing new (the incremental promise, end
  to end).
"""

import csv
import datetime
import io

import pytest
import time_machine

from core.models import BookingPeriod, CalendarExportMark, Collection, Thing

pytestmark = pytest.mark.django_db

URL = "/api/v1/collections/{code}/calendar-export/"
TODAY = datetime.date(2026, 9, 10)


@pytest.fixture(autouse=True)
def _frozen_today():
    with time_machine.travel(TODAY):
        yield


def _loan(collection, owner, requester, *, code="BKG001", start=TODAY + datetime.timedelta(days=5)):
    thing = Thing.objects.create(
        code=f"T{code[-5:]}", type="LEND_THING", owner=owner, headline="Taladro", status="ACTIVE"
    )
    collection.things.add(thing)
    return BookingPeriod.objects.create(
        code=code,
        thing_code=thing,
        thing_type="LEND_THING",
        requester_code=requester,
        requester_email=requester.email,
        owner_code=owner,
        start_date=start,
        end_date=start + datetime.timedelta(days=3),
        status="ACCEPTED",
    )


class TestWhoMayDownloadIt:
    def test_a_plain_member_gets_403(self, authenticated_client2, user, user2, collection):
        collection.invites.add(user2)
        res = authenticated_client2.post(URL.format(code=collection.code))
        assert res.status_code == 403

    def test_a_stranger_gets_403(self, authenticated_client2, user, collection):
        assert authenticated_client2.post(URL.format(code=collection.code)).status_code == 403

    def test_an_unknown_collection_is_404(self, authenticated_client):
        assert authenticated_client.post(URL.format(code="NOPE01")).status_code == 404

    def test_the_owner_gets_the_file(self, authenticated_client, user, user2, collection):
        _loan(collection, user, user2)
        res = authenticated_client.post(URL.format(code=collection.code))
        assert res.status_code == 200

    def test_a_co_owner_gets_the_file(self, authenticated_client2, user, user2, collection):
        collection.mode = Collection.Mode.PROPRIETARY
        collection.save()
        collection.invites.add(user2)
        collection.co_owners.add(user2)
        _loan(collection, user, user2)

        res = authenticated_client2.post(URL.format(code=collection.code))

        assert res.status_code == 200
        assert int(res["X-Calendar-Events"]) == 1


class TestPostOnly:
    def test_a_get_is_405_and_marks_nothing(self, authenticated_client, user, user2, collection):
        _loan(collection, user, user2)

        res = authenticated_client.get(URL.format(code=collection.code))

        assert res.status_code == 405
        assert not CalendarExportMark.objects.exists()


class TestTheFile:
    def test_it_is_a_named_csv_attachment_no_cache_may_keep(
        self, authenticated_client, user, user2, collection
    ):
        _loan(collection, user, user2)

        res = authenticated_client.post(URL.format(code=collection.code))

        assert res["Content-Type"].startswith("text/csv")
        assert f'filename="{collection.code}-calendar.csv"' in res["Content-Disposition"]
        assert res["Cache-Control"] == "private, no-store"
        assert res["X-Calendar-Events"] == "1"
        header = next(csv.reader(io.StringIO(res.content.decode())))
        assert header[0] == "Subject" and "All Day Event" in header

    def test_the_second_download_of_the_day_brings_nothing_new(
        self, authenticated_client, user, user2, collection
    ):
        _loan(collection, user, user2)

        first = authenticated_client.post(URL.format(code=collection.code))
        second = authenticated_client.post(URL.format(code=collection.code))

        assert first["X-Calendar-Events"] == "1"
        assert second["X-Calendar-Events"] == "0"
        # header only, no data rows
        assert len(second.content.decode().strip().splitlines()) == 1

    def test_a_reservation_confirmed_between_downloads_shows_up_next_time(
        self, authenticated_client, user, user2, collection
    ):
        _loan(collection, user, user2, code="BKG010")
        authenticated_client.post(URL.format(code=collection.code))

        _loan(
            collection,
            user,
            user2,
            code="BKG011",
            start=TODAY + datetime.timedelta(days=30),
        )
        res = authenticated_client.post(URL.format(code=collection.code))

        assert res["X-Calendar-Events"] == "1"
        rows = list(csv.DictReader(io.StringIO(res.content.decode())))
        assert len(rows) == 1

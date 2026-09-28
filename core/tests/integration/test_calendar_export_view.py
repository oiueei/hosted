"""POST /api/v1/collections/{code}/calendar-export/ — the calendar .ics download.

Behaviours guarded here:

- only a curator (owner or co-owner) can pull the file; a plain member and a
  stranger both get 403;
- it is **POST-only** — a bare GET gets DRF's default 405 (the view declares no
  ``get``); kept POST for contract stability with the frontend, per the view's
  own docstring, not because the call still mutates anything — it doesn't;
- the response is an iCalendar attachment named ``{code}-calendar.ics``, typed
  ``text/calendar``, tagged ``no-store`` (it carries member names) and carrying
  the event count in ``X-Calendar-Events``;
- a second POST the same day carries the **same** events, not an empty file —
  the stable per-booking UID (``calendar_export_service``) is what makes
  re-importing idempotent, which is what retired the old incremental watermark
  (``CalendarExportMark``, end to end: this view never writes one any more).
"""

import datetime

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
    def test_a_get_is_405(self, authenticated_client, user, user2, collection):
        _loan(collection, user, user2)

        res = authenticated_client.get(URL.format(code=collection.code))

        assert res.status_code == 405


def _uids(content):
    """The UID of every VEVENT in a downloaded ``.ics`` body, in file order."""
    return [
        line.split(":", 1)[1].strip()
        for line in content.decode().splitlines()
        if line.startswith("UID:")
    ]


class TestTheFile:
    def test_it_is_a_named_ics_attachment_no_cache_may_keep(
        self, authenticated_client, user, user2, collection
    ):
        _loan(collection, user, user2)

        res = authenticated_client.post(URL.format(code=collection.code))

        assert res["Content-Type"].startswith("text/calendar")
        assert f'filename="{collection.code}-calendar.ics"' in res["Content-Disposition"]
        assert res["Cache-Control"] == "private, no-store"
        assert res["X-Calendar-Events"] == "1"
        body = res.content.decode()
        assert body.startswith("BEGIN:VCALENDAR\r\n")
        assert body.endswith("END:VCALENDAR\r\n")
        assert body.count("BEGIN:VEVENT") == 1

    def test_a_second_download_the_same_day_carries_the_same_event_not_an_empty_file(
        self, authenticated_client, user, user2, collection
    ):
        _loan(collection, user, user2)

        first = authenticated_client.post(URL.format(code=collection.code))
        second = authenticated_client.post(URL.format(code=collection.code))

        assert first["X-Calendar-Events"] == second["X-Calendar-Events"] == "1"
        assert _uids(second.content) == _uids(first.content)
        # No watermark, ever — the stable UID is what makes re-import safe.
        assert not CalendarExportMark.objects.exists()

    def test_a_reservation_confirmed_between_downloads_joins_the_earlier_one(
        self, authenticated_client, user, user2, collection
    ):
        _loan(collection, user, user2, code="BKG010")
        first = authenticated_client.post(URL.format(code=collection.code))

        _loan(
            collection,
            user,
            user2,
            code="BKG011",
            start=TODAY + datetime.timedelta(days=30),
        )
        second = authenticated_client.post(URL.format(code=collection.code))

        assert second["X-Calendar-Events"] == "2"
        # Both bookings ship — the earlier one is not dropped for having gone
        # out before, since there is no watermark left to consult.
        assert set(_uids(second.content)) == {"BKG010@oiueei", "BKG011@oiueei"}
        assert _uids(first.content) == ["BKG010@oiueei"]


class TestACrossOriginClientCanReadTheCount:
    """The event count rides only in ``X-Calendar-Events``. A frontend on
    another domain (a documented deployment shape) cannot see a custom response
    header unless it is in ``Access-Control-Expose-Headers`` — without it the
    SPA reads a missing count as 0 and skips a download the server actually
    built. ``CORS_EXPOSE_HEADERS`` in ``base.py`` names it; this pins that the
    header actually reaches such a client.
    """

    def test_the_count_and_filename_headers_are_exposed_cross_origin(
        self, authenticated_client, user, user2, collection
    ):
        _loan(collection, user, user2)

        res = authenticated_client.post(
            URL.format(code=collection.code),
            HTTP_ORIGIN="http://localhost:3000",
        )

        exposed = {h.strip().lower() for h in res["Access-Control-Expose-Headers"].split(",")}
        assert "x-calendar-events" in exposed
        assert "content-disposition" in exposed

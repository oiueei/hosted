"""The collection calendar export — one CSV row per date-based reservation.

The behaviours this file guards:

- a confirmed loan/rental/reservation becomes exactly one all-day event that
  spans its block, in Google Calendar's column order;
- a reservation already handed to this collection's calendar is never in a
  second download (the "solo lo nuevo" promise);
- what is *not* a calendar commitment — a pending hold, a rejected one, a
  gift/sale with no dates, a booking that already ended — stays out;
- an owner headline that starts with ``=`` cannot become a spreadsheet formula
  in the exported cell;
- the same booking, exported for two collections, is tracked per collection.
"""

import csv
import datetime
import io

import pytest
import time_machine

from core.models import BookingPeriod, CalendarExportMark, Collection, Thing, User
from core.services.calendar_export_service import (
    CALENDAR_TEXTS,
    CSV_COLUMNS,
    build_calendar_export,
    calendar_filename,
)

pytestmark = pytest.mark.django_db

TODAY = datetime.date(2026, 9, 10)


@pytest.fixture(autouse=True)
def _frozen_today():
    # Every "future / in progress / past" assertion below is relative to TODAY;
    # freeze the clock so the suite doesn't rot the day these dates go stale.
    with time_machine.travel(TODAY):
        yield


def _rows(csv_bytes):
    return list(csv.DictReader(io.StringIO(csv_bytes.decode("utf-8"))))


@pytest.fixture
def owner(db):
    return User.objects.create(code="OWN001", email="own@example.com", name="Olga")


@pytest.fixture
def member(db):
    return User.objects.create(code="MEM001", email="mem@example.com", name="Júlia")


@pytest.fixture
def group(owner):
    # A real curated group has a language; the standalone default is English and
    # the TestLanguage class covers that path explicitly.
    return Collection.objects.create(
        code="GRP001", owner=owner, headline="El taller", language="es"
    )


def _thing(owner, code="THG001", thing_type="LEND_THING", headline="Taladre", location=""):
    return Thing.objects.create(
        code=code,
        type=thing_type,
        owner=owner,
        headline=headline,
        location=location,
        status="ACTIVE",
    )


def _booking(
    thing,
    member,
    owner,
    *,
    code="BKG001",
    thing_type=None,
    start=TODAY + datetime.timedelta(days=3),
    days=3,
    status="ACCEPTED",
    deposit=None,
    note="",
):
    return BookingPeriod.objects.create(
        code=code,
        thing_code=thing,
        thing_type=thing_type or thing.type,
        requester_code=member,
        requester_email=member.email,
        owner_code=owner,
        start_date=start,
        end_date=start + datetime.timedelta(days=days),
        status=status,
        deposit_amount=deposit,
        project_note=note,
    )


class TestOneEventPerReservation:
    def test_a_confirmed_loan_is_one_all_day_event_over_the_days_it_is_out(
        self, group, owner, member
    ):
        thing = _thing(owner, location="Nau 3")
        group.things.add(thing)
        # picked up the 14th, back the 17th → out on 14/15/16, free again the 17th
        _booking(thing, member, owner, start=datetime.date(2026, 9, 14), days=3)

        csv_bytes, count = build_calendar_export(group)

        assert count == 1
        (row,) = _rows(csv_bytes)
        assert row["Subject"] == "Préstamo: Taladre → Júlia"  # es default
        assert row["All Day Event"] == "True"
        assert row["Start Time"] == "" and row["End Time"] == ""
        assert row["Start Date"] == "09/14/2026"  # MM/DD/YYYY, Google's importer
        # OIUEEI's end_date and Google's CSV End Date are both exclusive — the
        # 17th is the day it is free again, so the event ends there and the 17th
        # stays open for the next booking.
        assert row["End Date"] == "09/17/2026"
        assert row["Location"] == "Nau 3"
        assert row["Private"] == "True"
        assert "Devolución el 17/09/2026" in row["Description"]

    def test_a_weeks_loan_blocks_seven_days_and_leaves_the_return_day_open(
        self, group, owner, member
    ):
        # CA's rule, verified against a real Google import (2026-09-10): pick up
        # Monday the 14th, return Monday the 21st → the 14th–20th are blocked and
        # the 21st is bookable again.
        thing = _thing(owner)
        group.things.add(thing)
        _booking(thing, member, owner, start=datetime.date(2026, 9, 14), days=7)

        (row,) = _rows(build_calendar_export(group)[0])

        assert row["Start Date"] == "09/14/2026"
        assert row["End Date"] == "09/21/2026"  # exclusive: covers 14–20, frees 21

    def test_the_header_is_googles_exact_column_order(self, group, owner, member):
        thing = _thing(owner)
        group.things.add(thing)
        _booking(thing, member, owner)

        csv_bytes, _ = build_calendar_export(group)

        header = next(csv.reader(io.StringIO(csv_bytes.decode("utf-8"))))
        assert header == CSV_COLUMNS
        assert header[:6] == [
            "Subject",
            "Start Date",
            "Start Time",
            "End Date",
            "End Time",
            "All Day Event",
        ]

    def test_a_one_day_reservation_blocks_exactly_that_day(self, group, owner, member):
        thing = _thing(owner, thing_type="RESERVE_THING")
        group.things.add(thing)
        # request_reservation stores end_date = start + duration, so a 1-day
        # reservation has end_date = start + 1 — the exclusive End Date that
        # Google renders as the single booked day.
        _booking(
            thing,
            member,
            owner,
            thing_type="RESERVE_THING",
            start=datetime.date(2026, 9, 20),
            days=1,
        )

        (row,) = _rows(build_calendar_export(group)[0])

        assert row["Start Date"] == "09/20/2026"
        assert row["End Date"] == "09/21/2026"  # exclusive → Google shows only the 20th

    def test_a_multi_day_reservation_blocks_every_booked_day(self, group, owner, member):
        # A 4-day reservation blocks all 4 days (unlike a loan, whose "return
        # day" is free) — end_date = start + 4, exclusive, so Google renders
        # 20/21/22/23.
        thing = _thing(owner, thing_type="RESERVE_THING")
        group.things.add(thing)
        _booking(
            thing,
            member,
            owner,
            thing_type="RESERVE_THING",
            start=datetime.date(2026, 9, 20),
            days=4,
        )

        (row,) = _rows(build_calendar_export(group)[0])

        assert row["Start Date"] == "09/20/2026"
        assert row["End Date"] == "09/24/2026"  # covers 20, 21, 22, 23

    def test_a_deposit_and_a_project_note_reach_the_description(self, group, owner, member):
        loan = _thing(owner, code="THG010", thing_type="RENT_THING")
        space = _thing(owner, code="THG011", thing_type="RESERVE_THING", headline="Sala")
        group.things.add(loan, space)
        _booking(loan, member, owner, code="BKG010", thing_type="RENT_THING", deposit="25.00")
        _booking(
            space,
            member,
            owner,
            code="BKG011",
            thing_type="RESERVE_THING",
            note="Ensayo de teatro",
        )

        rows = {r["Subject"]: r["Description"] for r in _rows(build_calendar_export(group)[0])}

        assert "Fianza: 25.00" in rows["Alquiler: Taladre → Júlia"]
        assert "Proyecto: Ensayo de teatro" in rows["Reserva: Sala — Júlia"]


class TestOnlyRealCommitments:
    def test_a_pending_hold_is_not_a_calendar_event(self, group, owner, member):
        thing = _thing(owner)
        group.things.add(thing)
        _booking(thing, member, owner, status="PENDING")

        _, count = build_calendar_export(group)

        assert count == 0

    @pytest.mark.parametrize("status", ["REJECTED", "CANCELLED", "EXPIRED"])
    def test_a_settled_or_dead_hold_is_not_exported(self, group, owner, member, status):
        thing = _thing(owner)
        group.things.add(thing)
        _booking(thing, member, owner, status=status)

        _, count = build_calendar_export(group)

        assert count == 0

    @pytest.mark.parametrize("thing_type", ["GIFT_THING", "SELL_THING"])
    def test_a_dateless_gift_or_sale_is_never_in_the_calendar(
        self, group, owner, member, thing_type
    ):
        thing = _thing(owner, thing_type=thing_type)
        group.things.add(thing)
        BookingPeriod.objects.create(
            code="BKG050",
            thing_code=thing,
            thing_type=thing_type,
            requester_code=member,
            requester_email=member.email,
            owner_code=owner,
            status="ACCEPTED",
        )

        _, count = build_calendar_export(group)

        assert count == 0

    def test_a_reservation_that_already_ended_is_dropped(self, group, owner, member):
        thing = _thing(owner)
        group.things.add(thing)
        _booking(thing, member, owner, start=TODAY - datetime.timedelta(days=10), days=3)

        _, count = build_calendar_export(group)

        assert count == 0

    def test_a_reservation_in_progress_today_is_kept(self, group, owner, member):
        thing = _thing(owner)
        group.things.add(thing)
        # started before today, ends after today — "en curso"
        _booking(thing, member, owner, start=TODAY - datetime.timedelta(days=1), days=5)

        _, count = build_calendar_export(group)

        assert count == 1


class TestIncremental:
    def test_a_reservation_already_downloaded_is_not_in_the_next_file(self, group, owner, member):
        thing = _thing(owner)
        group.things.add(thing)
        _booking(thing, member, owner)

        first_bytes, first_count = build_calendar_export(group)
        second_bytes, second_count = build_calendar_export(group)

        assert first_count == 1
        assert second_count == 0
        assert _rows(second_bytes) == []  # header only
        assert CalendarExportMark.objects.filter(collection=group).count() == 1

    def test_a_reservation_confirmed_after_the_last_download_is_picked_up(
        self, group, owner, member
    ):
        thing = _thing(owner)
        group.things.add(thing)
        _booking(thing, member, owner, code="BKG100")

        build_calendar_export(group)
        _booking(thing, member, owner, code="BKG101", start=TODAY + datetime.timedelta(days=20))

        _, count = build_calendar_export(group)

        assert count == 1
        assert {m.booking_id for m in CalendarExportMark.objects.filter(collection=group)} == {
            "BKG100",
            "BKG101",
        }

    def test_the_watermark_is_per_collection_not_per_booking(self, owner, member):
        # A thing lives in two curated collections. Exporting one must not
        # silence the reservation for the other.
        thing = _thing(owner)
        a = Collection.objects.create(code="GRPA00", owner=owner, headline="A")
        b = Collection.objects.create(code="GRPB00", owner=owner, headline="B")
        a.things.add(thing)
        b.things.add(thing)
        _booking(thing, member, owner)

        _, a_count = build_calendar_export(a)
        _, b_count = build_calendar_export(b)

        assert a_count == 1
        assert b_count == 1

    def test_the_same_reservation_cannot_be_marked_twice_for_one_collection(
        self, group, owner, member
    ):
        from django.db import IntegrityError

        thing = _thing(owner)
        group.things.add(thing)
        booking = _booking(thing, member, owner)
        CalendarExportMark.objects.create(collection=group, booking=booking)

        with pytest.raises(IntegrityError):
            CalendarExportMark.objects.create(collection=group, booking=booking)


class TestSpreadsheetFormulaInjection:
    FORMULA_PREFIXES = ("=", "+", "-", "@")

    def test_no_exported_cell_can_be_read_as_a_formula(self, group, owner, member):
        # The serializer rejects these on input; the export must not depend on
        # that having happened — a row can predate the guard or arrive by import.
        thing = _thing(owner, headline="=cmd|calc", location="-2+3")
        group.things.add(thing)
        _booking(thing, member, owner, thing_type="RESERVE_THING", note="@SUM(A1)")
        thing.type = "RESERVE_THING"
        thing.save()

        (row,) = _rows(build_calendar_export(group)[0])

        for column, cell in row.items():
            head = cell.lstrip()[:1]
            assert head not in self.FORMULA_PREFIXES or cell.startswith("'"), (column, cell)

    def test_a_location_that_is_a_formula_char_is_the_one_cell_that_needs_the_quote(
        self, group, owner, member
    ):
        # Location is the only cell whose first character is raw owner content
        # (Subject/Description always start with a label), so it is where the
        # quote actually does work.
        thing = _thing(owner, location="-1+2")
        group.things.add(thing)
        _booking(thing, member, owner)

        (row,) = _rows(build_calendar_export(group)[0])

        assert row["Location"] == "'-1+2"


class TestLanguage:
    def test_events_speak_the_collections_language(self, group, owner, member):
        group.language = "ca"
        group.save()
        thing = _thing(owner)
        group.things.add(thing)
        _booking(thing, member, owner)

        (row,) = _rows(build_calendar_export(group)[0])

        assert row["Subject"].startswith("Préstec:")  # ca, not es "Préstamo:"

    def test_the_downloading_curator_language_wins_over_the_group(self, group, owner, member):
        group.language = "ca"
        group.save()
        owner.language = "en"
        owner.save()
        thing = _thing(owner)
        group.things.add(thing)
        _booking(thing, member, owner)

        (row,) = _rows(build_calendar_export(group, user=owner)[0])

        assert row["Subject"].startswith("Loan:")

    def test_a_localized_headline_map_resolves_to_that_language(self, group, owner, member):
        group.language = "ca"
        group.save()
        thing = _thing(owner, headline='{"es": "Taladro", "ca": "Trepant"}')
        group.things.add(thing)
        _booking(thing, member, owner)

        (row,) = _rows(build_calendar_export(group)[0])

        assert "Trepant" in row["Subject"]
        assert "{" not in row["Subject"]

    def test_a_deployment_language_the_catalogue_lacks_falls_back_to_english(
        self, group, owner, member, settings
    ):
        settings.EMAIL_LANGUAGE = "fi"
        group.language = ""  # inherit the (unknown) deployment default
        group.save()
        thing = _thing(owner)
        group.things.add(thing)
        _booking(thing, member, owner)

        (row,) = _rows(build_calendar_export(group)[0])

        assert row["Subject"].startswith("Loan:")


class TestMemberIdentity:
    def test_a_member_with_no_display_name_is_a_member_not_a_blank_or_an_email(
        self, group, owner, member
    ):
        member.name = ""
        member.save()
        thing = _thing(owner)
        group.things.add(thing)
        _booking(thing, member, owner)

        (row,) = _rows(build_calendar_export(group)[0])

        assert row["Subject"].endswith("un miembro")
        assert member.email not in row["Subject"]


class TestCatalogueParity:
    def test_every_language_carries_the_same_keys(self):
        reference = set(CALENDAR_TEXTS["en"])
        for lang, texts in CALENDAR_TEXTS.items():
            assert set(texts) == reference, lang

    def test_there_is_a_subject_line_for_every_date_based_type(self):
        from core.models.booking import DATE_BASED_TYPES

        for lang, texts in CALENDAR_TEXTS.items():
            for thing_type in DATE_BASED_TYPES:
                assert texts[f"subject_{thing_type}"], (lang, thing_type)


def test_the_filename_matches_the_stats_csv_shape():
    assert calendar_filename("ABC123") == "ABC123-calendar.csv"


def test_a_mark_names_its_collection_and_booking(group, owner, member):
    # The admin row an operator reads when a reservation was exported twice.
    thing = _thing(owner)
    group.things.add(thing)
    booking = _booking(thing, member, owner, code="BKG777")
    mark = CalendarExportMark.objects.create(collection=group, booking=booking)

    assert group.code in str(mark) and "BKG777" in str(mark)

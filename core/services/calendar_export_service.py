"""The collection calendar export — date-based reservations as a Google Calendar CSV.

A curator downloads their collection's upcoming loans, rentals and on-site
reservations as a CSV in Google Calendar's import column order. Each reservation
is **one all-day event covering the days the thing is unavailable** — from the
pickup day up to (not including) the return day, since the return day is already
free for the next booking. A one-week loan picked up Monday blocks Mon–Sun and
leaves the next Monday open.

**Incremental.** Each download carries only reservations not delivered before
and records them in ``CalendarExportMark`` (per collection — the curators share
the catalogue). ``build_calendar_export`` reads and marks in one call, inside a
transaction that locks the collection row, so two curators pressing the button
at once can't both receive the same reservation and a reservation is either in
this file *and* marked or in neither.

Everything user-written that reaches a cell — a thing headline, a member name, a
project note — goes through ``_csv_cell``, which neutralises a leading
``= + - @`` (spreadsheet-formula injection) the way ``collection_stats_rows``
avoids it by construction. Owner headlines that carry one text per language
(inline JSON, O6) resolve to the collection's language.
"""

import csv
import io

from django.db import transaction
from django.utils import timezone

from core.models import BookingPeriod, CalendarExportMark, Collection
from core.models.booking import DATE_BASED_TYPES
from core.models.thing import Thing
from core.services.email_service import resolve_email_language
from core.utils import resolve_localized

# Google Calendar's documented CSV import column order.
CSV_COLUMNS = [
    "Subject",
    "Start Date",
    "Start Time",
    "End Date",
    "End Time",
    "All Day Event",
    "Description",
    "Location",
    "Private",
]

# The date format Google Calendar's CSV importer parses — MM/DD/YYYY (US),
# regardless of the account's locale. The one format it reads reliably.
_GCAL_DATE = "%m/%d/%Y"

# Google Calendar's CSV importer treats an all-day event's End Date as
# **exclusive** — a row `09/14 … 09/16` imports as an event covering the 14th
# and 15th only (verified against a real import, 2026-09-10). That is exactly
# OIUEEI's own `end_date`: the day the thing is back / the space is free again,
# free for the next booking (matches `BookingPeriod.has_overlap` and the
# availability walk). So the two map straight across — a one-week loan picked up
# Monday the 14th has `end_date` the 21st, blocks the 14th–20th on the calendar,
# and leaves the 21st open, which is the rule. Do NOT "fix" this by subtracting
# a day; that reintroduces the bug it documents.

# Spreadsheet-formula prefixes (CSV injection). Mirrors
# ``core.validators._FORMULA_PREFIXES`` — kept local rather than importing a
# private name for a four-tuple.
_FORMULA_PREFIXES = ("=", "+", "-", "@")

# One text catalogue per language, kept in parity by
# ``test_calendar_export_service.py`` (the pattern ``export_service.README_TEXTS``
# uses). Not part of the email catalogue: this is a file for a machine, not a
# message, and the operator-facing senders that carry data rather than copy are
# already outside ``email_texts``.
CALENDAR_TEXTS = {
    "en": {
        "subject_LEND_THING": "Loan: {thing} → {person}",
        "subject_RENT_THING": "Rental: {thing} → {person}",
        "subject_RESERVE_THING": "Reservation: {thing} — {person}",
        "a_member": "a member",
        "return_by": "Return by {date}",
        "deposit": "Deposit: {amount}",
        "note": "Project: {note}",
        "provenance": "OIUEEI · {collection}",
    },
    "es": {
        "subject_LEND_THING": "Préstamo: {thing} → {person}",
        "subject_RENT_THING": "Alquiler: {thing} → {person}",
        "subject_RESERVE_THING": "Reserva: {thing} — {person}",
        "a_member": "un miembro",
        "return_by": "Devolución el {date}",
        "deposit": "Fianza: {amount}",
        "note": "Proyecto: {note}",
        "provenance": "OIUEEI · {collection}",
    },
    "ca": {
        "subject_LEND_THING": "Préstec: {thing} → {person}",
        "subject_RENT_THING": "Lloguer: {thing} → {person}",
        "subject_RESERVE_THING": "Reserva: {thing} — {person}",
        "a_member": "un membre",
        "return_by": "Devolució el {date}",
        "deposit": "Dipòsit: {amount}",
        "note": "Projecte: {note}",
        "provenance": "OIUEEI · {collection}",
    },
}


def _csv_cell(value):
    """A cell no spreadsheet will read as a formula. ``None`` becomes ``""``."""
    text = "" if value is None else str(value)
    if text[:1] in _FORMULA_PREFIXES:
        return "'" + text
    return text


def _ddmy(value):
    """A date the way OIUEEI shows dates to people everywhere else — DD/MM/YYYY."""
    return value.strftime("%d/%m/%Y") if value else ""


def _pending_bookings(collection):
    """The collection's date-based, confirmed, not-yet-finished reservations that
    haven't been exported for this collection before, oldest start first."""
    today = timezone.localdate()
    marked = CalendarExportMark.objects.filter(collection=collection).values_list(
        "booking_id", flat=True
    )
    return (
        BookingPeriod.objects.filter(
            thing_code__collections=collection,
            thing_type__in=DATE_BASED_TYPES,
            status=BookingPeriod.Status.ACCEPTED,
            end_date__gte=today,
        )
        .exclude(code__in=marked)
        .select_related("thing_code", "requester_code")
        .distinct()
        .order_by("start_date", "code")
    )


def _row(booking, texts, lang, collection_headline):
    """One CSV row (a dict keyed by ``CSV_COLUMNS``) for one reservation."""
    thing = booking.thing_code
    headline = resolve_localized(thing.headline, lang)
    person = (booking.requester_code.name or "").strip() or texts["a_member"]
    subject = texts[f"subject_{booking.thing_type}"].format(thing=headline, person=person)

    # Both dates map straight to Google's columns: OIUEEI's exclusive `end_date`
    # is exactly what Google's exclusive CSV End Date wants (see _GCAL_DATE note).
    start = booking.start_date
    end = booking.end_date

    description = []
    if booking.thing_type in (Thing.Type.LEND_THING, Thing.Type.RENT_THING):
        description.append(texts["return_by"].format(date=_ddmy(booking.end_date)))
        if booking.deposit_amount:
            description.append(texts["deposit"].format(amount=booking.deposit_amount))
    if booking.thing_type == Thing.Type.RESERVE_THING and booking.project_note.strip():
        description.append(texts["note"].format(note=booking.project_note.strip()))
    description.append(
        texts["provenance"].format(collection=resolve_localized(collection_headline, lang))
    )

    return {
        "Subject": _csv_cell(subject),
        "Start Date": start.strftime(_GCAL_DATE),
        "Start Time": "",
        "End Date": end.strftime(_GCAL_DATE),
        "End Time": "",
        "All Day Event": "True",
        "Description": _csv_cell(" — ".join(description)),
        "Location": _csv_cell((thing.location or "").strip()),
        "Private": "True",
    }


def _csv_bytes(rows):
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_COLUMNS)
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def calendar_filename(code):
    """``ABC123-calendar.csv`` — matches the stats CSV's shape."""
    return f"{code}-calendar.csv"


def build_calendar_export(collection, user=None):
    """Return ``(csv_bytes, count)`` for the reservations not yet exported.

    Reads the pending reservations, renders the CSV, and records every one as
    delivered — atomically, behind a lock on the collection row so two
    simultaneous downloads can't each carry the same reservation. ``count`` is
    how many events the file holds (0 ⇒ header only).

    The event copy speaks the downloading curator's language, then the group's,
    then the deployment default — the same hierarchy every email follows
    (``resolve_email_language``).
    """
    lang = resolve_email_language(user=user, collection=collection)
    texts = CALENDAR_TEXTS.get(lang, CALENDAR_TEXTS["en"])

    with transaction.atomic():
        # Serialise concurrent exports of this collection (same pattern as
        # ThingBulkCreateView's ceiling re-check).
        Collection.objects.select_for_update().get(pk=collection.pk)
        bookings = list(_pending_bookings(collection))
        rows = [_row(booking, texts, lang, collection.headline) for booking in bookings]
        CalendarExportMark.objects.bulk_create(
            [CalendarExportMark(collection=collection, booking=booking) for booking in bookings]
        )

    return _csv_bytes(rows), len(rows)

"""The collection calendar export — date-based reservations as iCalendar (.ics).

A curator downloads their collection's upcoming loans, rentals and on-site
reservations as an RFC 5545 VCALENDAR. A whole-day booking (every LEND/RENT,
and a DAY-unit RESERVE) is **one all-day event covering the days the thing is
unavailable** — from the pickup day up to (not including) the return day, since
the return day is already free for the next booking. A one-week loan picked up
Monday blocks Mon–Sun and leaves the next Monday open. An **HOUR-unit
RESERVE_THING** (`booking.start_time` set) is instead one *timed* event,
rendered in UTC so the file needs no VTIMEZONE and imports at the same wall
clock everywhere.

**Why .ics and not the CSV this used to be.** Google Calendar's CSV importer
reads dates in the format of the *importing account* — an early adopter's
day/month account read ``10/01/2026`` as the 10th of January (CA's production
report, 2026-09-28; the 2026-09-10 "verified" import was against a US-locale
account, so the MM/DD/YYYY assumption was never true in general). iCalendar's
dates are unambiguous and carry their timezone, and Google, Apple Calendar and
Outlook all import them — on a phone, opening the file is enough.

**Every upcoming reservation, not just the new ones.** Each VEVENT's UID is
``{booking.code}@oiueei``, stable across downloads, so a calendar that
re-imports the file updates its events in place instead of duplicating them —
which is what made the old incremental watermark unnecessary. The
``CalendarExportMark`` model (and its lock) is therefore **dormant**: this
module neither reads nor writes it, the row stays in the schema for the
release after this one, and it is dropped then (the two-release rule
``reservation_max_hours`` followed).

Everything user-written that reaches a TEXT property — a thing headline, a
member name, a project note — is escaped per RFC 5545 §3.3.11 (backslash,
semicolon, comma, newline), which replaces the spreadsheet-formula guard the
CSV needed. Owner headlines that carry one text per language (inline JSON, O6)
resolve to the collection's language.
"""

import datetime
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone

from core.models import BookingPeriod
from core.models.booking import DATE_BASED_TYPES
from core.models.thing import Thing
from core.services.email_service import resolve_email_language
from core.utils import resolve_localized

# RFC 5545 §3.1: content lines are delimited by CRLF and must not be longer
# than 75 OCTETS — bytes, not characters, so a multibyte UTF-8 sequence must
# never be split. A longer line folds with CRLF followed by a single space.
_LINE_OCTETS = 75

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


def _esc(value):
    """A TEXT value per RFC 5545 §3.3.11 — backslash, semicolon and comma are
    escaped, and a line break becomes a literal ``\\n``. The escaping a TEXT
    property needs; the CSV's spreadsheet-formula guard has no equivalent here
    because nothing downstream evaluates a calendar entry as an expression."""
    text = "" if value is None else str(value)
    text = text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
    return text.replace("\r\n", "\\n").replace("\r", "\\n").replace("\n", "\\n")


def _fold(line):
    """One content line as the physical lines RFC 5545 allows — ≤75 octets each,
    continuations prefixed with a space, never splitting a UTF-8 character.

    The leading space on every continuation is the fold marker itself (RFC
    5545 §3.1): the unfolder strips exactly one such character from each
    continuation before rejoining. It must be *added* here, not merely
    budgeted for — a fold that reserves the octet but never writes the space
    silently eats the continuation's first real character on unfold instead
    (found reading the production `.ics` back: a headline or description long
    enough to fold came back missing one letter at each fold point)."""
    raw = line.encode("utf-8")
    if len(raw) <= _LINE_OCTETS:
        return [line]

    parts = []
    start = 0
    limit = _LINE_OCTETS
    first = True
    while start < len(raw):
        end = min(start + limit, len(raw))
        # Back off to a character boundary: a UTF-8 continuation byte is
        # 0b10xxxxxx, so step left while the byte we would cut at is one.
        while end < len(raw) and raw[end] & 0xC0 == 0x80:
            end -= 1
        piece = raw[start:end].decode("utf-8")
        parts.append(piece if first else " " + piece)
        start = end
        limit = _LINE_OCTETS - 1  # room for the next continuation's own leading space
        first = False
    return parts


def _ddmy(value):
    """A date the way OIUEEI shows dates to people everywhere else — DD/MM/YYYY."""
    return value.strftime("%d/%m/%Y") if value else ""


def _utc(day, clock):
    """A wall-clock time on ``day``, read in the deployment's timezone, as UTC.

    ``TIME_ZONE`` is the zone ``opening_hours`` and reservation times are
    written in, so it is the only honest reading of ``start_time``. UTC output
    is what lets the file carry no VTIMEZONE and still land on the right wall
    clock in every importing calendar.
    """
    local = datetime.datetime.combine(day, clock, tzinfo=ZoneInfo(settings.TIME_ZONE))
    return local.astimezone(datetime.timezone.utc)


def _fmt_utc(moment):
    return moment.strftime("%Y%m%dT%H%M%SZ")


def _upcoming_bookings(collection):
    """The collection's date-based, confirmed, not-yet-finished reservations,
    oldest start first. Every one of them — the stable UID is what keeps a
    re-import from duplicating, so there is no watermark to respect."""
    today = timezone.localdate()
    return (
        BookingPeriod.objects.filter(
            thing_code__collections=collection,
            thing_type__in=DATE_BASED_TYPES,
            status=BookingPeriod.Status.ACCEPTED,
            end_date__gte=today,
        )
        .select_related("thing_code", "requester_code")
        .distinct()
        .order_by("start_date", "code")
    )


def _event_lines(booking, texts, lang, collection_headline, now):
    """One VEVENT for one reservation."""
    thing = booking.thing_code
    headline = resolve_localized(thing.headline, lang)
    person = (booking.requester_code.name or "").strip() or texts["a_member"]
    summary = texts[f"subject_{booking.thing_type}"].format(thing=headline, person=person)

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

    lines = [
        "BEGIN:VEVENT",
        # Stable across downloads: a calendar that re-imports the file updates
        # this event in place instead of growing a duplicate.
        f"UID:{booking.code}@oiueei",
        f"DTSTAMP:{_fmt_utc(now)}",
    ]
    if booking.start_time is not None and booking.end_time is not None:
        # An HOUR-unit reservation: a timed event, both clock times on
        # `start_date`. Never `end_date`, which for an hourly booking stores
        # `start_date + 1` purely as the day-based "free again" marker every
        # other consumer reads — using it would push the event a day late.
        lines.append(f"DTSTART:{_fmt_utc(_utc(booking.start_date, booking.start_time))}")
        lines.append(f"DTEND:{_fmt_utc(_utc(booking.start_date, booking.end_time))}")
    else:
        # A whole-day booking: iCalendar's all-day DTEND is exclusive — exactly
        # OIUEEI's own `end_date`, the day the thing is free again (matches
        # `has_overlap` and the availability walk). A one-week loan picked up
        # Monday the 14th has `end_date` the 21st, blocks the 14th–20th, and
        # leaves the 21st open. Do NOT "fix" this by subtracting a day.
        lines.append(f"DTSTART;VALUE=DATE:{booking.start_date:%Y%m%d}")
        lines.append(f"DTEND;VALUE=DATE:{booking.end_date:%Y%m%d}")
    lines.append(f"SUMMARY:{_esc(summary)}")
    lines.append(f"DESCRIPTION:{_esc(' — '.join(description))}")
    location = (thing.location or "").strip()
    if location:
        lines.append(f"LOCATION:{_esc(location)}")
    lines.append("END:VEVENT")
    return lines


def _ics_bytes(bookings, texts, lang, collection):
    now = timezone.now().astimezone(datetime.timezone.utc)
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//OIUEEI//Calendar export//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_esc(resolve_localized(collection.headline, lang))}",
    ]
    for booking in bookings:
        lines.extend(_event_lines(booking, texts, lang, collection.headline, now))
    lines.append("END:VCALENDAR")

    physical = []
    for line in lines:
        physical.extend(_fold(line))
    return ("\r\n".join(physical) + "\r\n").encode("utf-8")


def calendar_filename(code):
    """``ABC123-calendar.ics`` — the stats CSV's shape, the iCalendar extension."""
    return f"{code}-calendar.ics"


def build_calendar_export(collection, user=None):
    """Return ``(ics_bytes, count)`` for every upcoming reservation.

    The whole future of the collection, not just what a previous download
    missed: the per-booking UID makes re-importing idempotent, which is what
    retired the incremental watermark — and that watermark was exactly what
    locked a curator out of downloading again after a failed import.
    ``CalendarExportMark`` is neither read nor written any more; the model stays
    in the schema, dormant, and is dropped in the release after this one.

    The event copy speaks the downloading curator's language, then the group's,
    then the deployment default — the same hierarchy every email follows
    (``resolve_email_language``).
    """
    lang = resolve_email_language(user=user, collection=collection)
    texts = CALENDAR_TEXTS.get(lang, CALENDAR_TEXTS["en"])

    bookings = list(_upcoming_bookings(collection))
    return _ics_bytes(bookings, texts, lang, collection), len(bookings)

// Rental-rule helpers (#7). Collections can offer a set of fixed rental lengths
// (in days) and restrict pickup/return to certain weekdays.

// Day-length presets an owner can offer, each with an i18n label key.
export const RENTAL_DURATION_PRESETS = [
  { days: 1, key: 'rental.d1' },
  { days: 2, key: 'rental.d2' },
  { days: 3, key: 'rental.d3' },
  { days: 7, key: 'rental.w1' },
  { days: 14, key: 'rental.w2' },
  { days: 21, key: 'rental.w3' },
  { days: 30, key: 'rental.m1' },
];

const KEY_BY_DAYS = Object.fromEntries(RENTAL_DURATION_PRESETS.map((p) => [p.days, p.key]));

// i18n label for a stored day-length (falls back to "{n}" for any non-preset value).
export const durationLabel = (days, t) => (KEY_BY_DAYS[days] ? t(KEY_BY_DAYS[days]) : String(days));

// Weekday values in Python's numbering (0=Mon … 6=Sun), matching the backend.
export const WEEKDAY_VALUES = [0, 1, 2, 3, 4, 5, 6];

// Localised weekday name for a Python weekday index. 2024-01-01 was a Monday, so
// we offset from it — no need for 49 hand-translated weekday strings.
export const weekdayLabel = (pyWeekday, lang) =>
  new Date(2024, 0, 1 + pyWeekday).toLocaleDateString(lang, { weekday: 'long' });

// Narrow single-letter weekday for the chip face (es → L M X J V S D). The full
// name still rides along as the chip's aria-label / title for accessibility.
export const weekdayNarrow = (pyWeekday, lang) =>
  new Date(2024, 0, 1 + pyWeekday).toLocaleDateString(lang, { weekday: 'narrow' });

// JS Date.getDay() (0=Sun … 6=Sat) → Python weekday (0=Mon … 6=Sun).
export const jsToPyWeekday = (jsDay) => (jsDay + 6) % 7;

// Parse a value to a Date at LOCAL midnight. A 'YYYY-MM-DD' string is split into
// its components so it lands on the intended local day — new Date('YYYY-MM-DD')
// parses as UTC midnight and shifts back a day in UTC-negative timezones (the
// flagship rental return-date bug). A Date (or anything else) is normalised to
// local midnight.
export const parseLocalDate = (value) => {
  if (typeof value === 'string') {
    const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(value);
    if (m) return new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  }
  const d = new Date(value);
  d.setHours(0, 0, 0, 0);
  return d;
};

// Date + N days (returns a new Date at local midnight).
export const addDays = (date, n) => {
  const d = parseLocalDate(date);
  d.setDate(d.getDate() + n);
  return d;
};

// 'YYYY-MM-DD' for a Date, built from local components (never UTC).
export const toISODate = (d) => {
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  return `${yyyy}-${mm}-${dd}`;
};

// The DateInputs show DD/MM/YYYY (the everyday convention in all three locales);
// the API and every helper above keep speaking ISO YYYY-MM-DD. These two convert
// at the component boundary — pure string work, no Date parsing, so timezone-proof.
export const DISPLAY_DATE_FORMAT = 'dd/MM/yyyy';

// 'YYYY-MM-DD' → 'DD/MM/YYYY' ('' for anything else).
export const isoToDisplay = (iso) => {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso || '');
  return m ? `${m[3]}/${m[2]}/${m[1]}` : '';
};

// Every date the app *displays* goes through here: 'DD/MM/YYYY', the everyday
// convention in all three of OIUEEI's locales (es/ca/en) and the one the date
// pickers and `closed_dates` already speak. Plain `toLocaleDateString(lang)`
// handed 'en' readers American MM/DD/YYYY, so a booking range read one way in
// the picker and another in the table. Accepts an ISO date, an ISO datetime or
// a Date; returns '' for anything unparseable (a null booking range renders
// blank, not 'Invalid Date').
export const formatDate = (value) => {
  if (!value) return '';
  const exact = isoToDisplay(value);
  if (exact) return exact;
  const d = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(d.getTime())) return '';
  const dd = String(d.getDate()).padStart(2, '0');
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  return `${dd}/${mm}/${d.getFullYear()}`;
};

// An ISO datetime *with* its clock time — 'DD/MM/YYYY HH:MM' in the reader's
// own timezone, formatDate plus local hours/minutes. The stamp a notification
// carries (`created`, when something happened) is the caller that needs it:
// `formatDate` deliberately drops the time it is composed of, so a reader in
// another timezone would see the event's UTC day alone. '' for anything
// unparseable, like formatDate (an absent stamp renders no line at all).
export const formatDateTime = (value) => {
  if (!value) return '';
  const d = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(d.getTime())) return '';
  const hh = String(d.getHours()).padStart(2, '0');
  const mi = String(d.getMinutes()).padStart(2, '0');
  return `${formatDate(d)} ${hh}:${mi}`;
};

// A booking's date/time range for a listing row — MyBookingsPage,
// OwnerBookingsPage, OwnerBookingsList — read straight off the API's own
// field names (`start_date`/`end_date` ISO dates, `start_time`/`end_time`
// 'HH:MM:SS' or absent). A loan or rental renders 'DD/MM/YYYY — DD/MM/YYYY',
// pickup to return. An HOUR-unit RESERVE_THING slot renders the date once
// plus both clock times: 'DD/MM/YYYY, HH:MM–HH:MM'. A DAY-unit reservation
// ends on its LAST day, inclusive — the date alone for one day — because its
// `end_date` is `start + duration`, the day the space is free again: a
// one-day reservation used to list as two days. `thingType` defaults to the
// booking's own `thing_type`; OwnerBookingsList's calendar rows don't carry
// one, so their card passes it. '' when there are no dates at all (GIFT/SELL).
export const formatBookingWhen = (booking, thingType = booking?.thing_type) => {
  if (!booking?.start_date || !booking?.end_date) return '';
  const date = formatDate(booking.start_date);
  if (booking.start_time && booking.end_time) {
    return `${date}, ${booking.start_time.slice(0, 5)}–${booking.end_time.slice(0, 5)}`;
  }
  if (thingType === 'RESERVE_THING') {
    const lastDay = formatDate(addDays(booking.end_date.slice(0, 10), -1));
    return lastDay === date ? date : `${date} — ${lastDay}`;
  }
  // A loan or rental for a single day: that day once, not "13/10/2026 — 13/10/2026".
  const returnDate = formatDate(booking.end_date);
  return returnDate === date ? date : `${date} — ${returnDate}`;
};

// What a request page is about to book (or just booked), read off the POST
// body it sends — the one thing both the pre-submit summary and the success
// notice can agree on. An HOUR-unit reservation: 'DD/MM/YYYY, HH:MM–HH:MM'. A
// DAY-unit one (`duration_days`): its LAST day, inclusive — 'DD/MM/YYYY' alone
// for a single day, else 'DD/MM/YYYY — DD/MM/YYYY' — never the `start +
// duration` the server stores as `end_date`, which is the day the space is
// free again. A loan or rental: pickup — return, as sent. '' for no dates.
export const formatRequestedWhen = (body) => {
  if (!body?.start_date) return '';
  const start = isoToDisplay(body.start_date);
  if (body.start_time && body.end_time) return `${start}, ${body.start_time}–${body.end_time}`;
  if (body.duration_days) {
    const days = Number(body.duration_days);
    if (days <= 1) return start;
    return `${start} — ${isoToDisplay(derivedReturnDate(body.start_date, days - 1))}`;
  }
  if (body.end_date) {
    const end = isoToDisplay(body.end_date);
    return end === start ? start : `${start} — ${end}`;
  }
  return start;
};

// 'DD/MM/YYYY' (loose D/M/YYYY accepted) → 'YYYY-MM-DD' ('' for malformed or
// impossible dates like 31/02, which HDS also flags via malformedDateErrorText).
export const displayToIso = (display) => {
  const m = /^(\d{1,2})\/(\d{1,2})\/(\d{4})$/.exec((display || '').trim());
  if (!m) return '';
  const [dd, mm, yyyy] = [Number(m[1]), Number(m[2]), Number(m[3])];
  const d = new Date(yyyy, mm - 1, dd);
  if (d.getFullYear() !== yyyy || d.getMonth() !== mm - 1 || d.getDate() !== dd) return '';
  return `${yyyy}-${String(mm).padStart(2, '0')}-${String(dd).padStart(2, '0')}`;
};

// Weekday rule: allowed when unrestricted, or the date's Python weekday is listed.
export const weekdayAllowed = (date, rentalWeekdays) =>
  rentalWeekdays.length === 0 ||
  rentalWeekdays.includes(jsToPyWeekday(parseLocalDate(date).getDay()));

// The collection's holiday / closure days (ISO strings) as a Set for O(1) lookup.
export const closedSet = (closedDates) => new Set(closedDates || []);

// Is `date` one of the collection's closure days (festivos)?
export const isClosedDate = (date, closed) => closed.has(toISODate(parseLocalDate(date)));

// Is `date` blocked for a PICKUP? A booking [s, e] blocks pickup on [s, e) — but
// NOT on its return day e, which is free for the next pickup (back-to-back
// handovers, mirroring BookingPeriod.has_overlap's strict overlap). A pickup on e
// is chained to the booking before it, which the server accepts.
export const isPickupBlocked = (date, blockedPeriods) => {
  const d = parseLocalDate(date);
  return blockedPeriods.some((period) => {
    const start = parseLocalDate(period.start_date);
    const end = parseLocalDate(period.end_date);
    return d >= start && d < end;
  });
};

// Would a rental of `len` days picked up on `pickup` strictly overlap any booking?
// Candidate range is [pickup, pickup+len]; it conflicts with an existing [s, e]
// iff they share an interior day (pickup < e AND s < return). Touching at a
// boundary — the derived return landing exactly on another booking's start, or a
// pickup on another booking's return day — is allowed.
export const rangeBlocked = (pickup, len, blockedPeriods) => {
  const p = parseLocalDate(pickup);
  const r = addDays(pickup, len);
  return blockedPeriods.some((period) => {
    const start = parseLocalDate(period.start_date);
    const end = parseLocalDate(period.end_date);
    return p < end && start < r;
  });
};

// LEND/RENT with free dates (no fixed lengths): the two pickers of the request form
// follow the SAME rules as the server and the card. Two of them:
//
// - **Chained handovers.** A booking [s, e] occupies the pickup on [s, e), and its
//   return day e is free for the next pickup. The server accepts a request
//   [start, end] unless it shares an interior day with a booking
//   (`BookingPeriod.has_overlap`: s < end AND e > start). Both pickers used to grey
//   out BOTH ends of every booking (the calendar *display* range), which blocked
//   picking up on another booking's return day and returning on another's pickup day
//   — two things the server allows (a card saying "available from
//   06/10" with a calendar that began on the 7th).
// - **The collection's weekdays** (`rental_weekdays`, Python's 0 = Monday; `[]` = any
//   day). The server demands them at BOTH ends — `Collection.rental_violation` answers
//   `rental_pickup_weekday` for the pickup and `rental_return_weekday` for the return —
//   and it does so with or without fixed lengths. The fixed-length form already applied
//   them (`isPickupDisabled`); the free form did not, so a Wednesday could be picked in
//   a "Saturdays only" collection and the server refused it on send. A day of the wrong weekday is out in both pickers, whatever the other
//   one holds: the return picker has no pickup to measure against until one is chosen,
//   and the weekday does not depend on it.
const MS_PER_DAY = 24 * 60 * 60 * 1000;

// The pickup picker: a day of a weekday the collection does not allow is out, a closure
// day is out, and so is any day a booking occupies ([s, e) — not its return day).
export const freePickupDisabled = (
  date,
  { rentalWeekdays = [], blockedPeriods = [], closedDates = [] }
) =>
  !weekdayAllowed(date, rentalWeekdays) ||
  isClosedDate(date, closedSet(closedDates)) ||
  isPickupBlocked(date, blockedPeriods);

// The return picker, given the pickup chosen (ISO string, or '' when there is none
// yet): a day of a weekday the collection does not allow is out; a closure day is out;
// so is a day before the pickup; so is a day whose stretch [pickup, return) runs over a
// booking — a return that lands exactly on another booking's pickup is the chained
// handover and stays open (`rangeBlocked`). With no pickup chosen there is no stretch to
// measure, so it is the pickup's rule.
export const freeReturnDisabled = (
  date,
  { pickup, rentalWeekdays = [], blockedPeriods = [], closedDates = [] }
) => {
  if (!weekdayAllowed(date, rentalWeekdays)) return true;
  if (isClosedDate(date, closedSet(closedDates))) return true;
  if (!pickup) return isPickupBlocked(date, blockedPeriods);
  const days = Math.round((parseLocalDate(date) - parseLocalDate(pickup)) / MS_PER_DAY);
  if (days < 0) return true;
  return rangeBlocked(pickup, days, blockedPeriods);
};

// Disable a pickup day when it — or, once a length is chosen, its return day or any
// day in between — breaks the weekday rule or overlaps an existing booking. The
// return day is pickup + length: a one-week rental picked up on a Wednesday is
// returned the NEXT Wednesday, so a single allowed weekday stays satisfiable. A
// day that is only another booking's return day stays selectable (back-to-back).
export const isPickupDisabled = (
  date,
  { rentalWeekdays, blockedPeriods, duration, closedDates = [] }
) => {
  const closed = closedSet(closedDates);
  if (!weekdayAllowed(date, rentalWeekdays)) return true;
  if (isClosedDate(date, closed)) return true; // no pickup on a closure day
  if (isPickupBlocked(date, blockedPeriods)) return true;
  if (duration) {
    const len = Number(duration);
    const ret = addDays(date, len);
    if (!weekdayAllowed(ret, rentalWeekdays)) return true;
    if (isClosedDate(ret, closed)) return true; // nor a return on one
    if (rangeBlocked(date, len, blockedPeriods)) return true;
  }
  return false;
};

// Derived return date (ISO string) for a pickup date + fixed length in days.
export const derivedReturnDate = (pickup, days) => toISODate(addDays(pickup, Number(days)));

// A stored `closed_dates` ISO list → the comma-separated DD/MM/YYYY line the
// owner edits. `["2026-12-25","2026-12-26"]` → "25/12/2026, 26/12/2026".
export const closedDatesToDisplay = (list) => (list || []).map(isoToDisplay).join(', ');

// RESERVE_THING pickup validity. Stricter than isPickupDisabled: the space is
// occupied for the WHOLE span, so EVERY day of [pickup, pickup+duration) must be
// an allowed weekday (not just pickup and the return day — a reservation can't
// straddle a closed day). Plus the usual overlap check. `rentalWeekdays` is the
// collection's `rental_weekdays`, reused as "days reservations are allowed".
export const reservationPickupDisabled = (
  date,
  { rentalWeekdays = [], blockedPeriods = [], duration, closedDates = [] }
) => {
  const len = Math.max(1, Number(duration) || 1);
  const closed = closedSet(closedDates);
  for (let offset = 0; offset < len; offset += 1) {
    const day = addDays(date, offset);
    if (rentalWeekdays.length && !weekdayAllowed(day, rentalWeekdays)) return true;
    if (isClosedDate(day, closed)) return true; // the space can't span a closure
  }
  return rangeBlocked(date, len, blockedPeriods);
};

// --- HOUR-unit RESERVE_THING: time-of-day helpers ---------------------------
//
// Everything below deals in "HH:MM" strings or plain minutes-since-midnight
// integers, mirroring `Collection.opening_hours` / a reservation's
// `start_time`/`end_time` exactly — there is no Date or timezone concept for a
// wall-clock time within one already-chosen day. Kept as pure functions on
// purpose: `Collection.day_opening_blocks` / `reservation_hour_violation` on
// the backend walk the identical shapes, and a client-side mirror that agreed
// with itself but not the server would just move the disagreement, not close it.

// "HH:MM" -> minutes since midnight.
export const parseHM = (hm) => {
  const [h, m] = hm.split(':').map(Number);
  return h * 60 + m;
};

// minutes since midnight -> "HH:MM".
export const formatHM = (minutes) => {
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
};

// The opening blocks for one JS Date, as `[{start, end}]` in minutes since
// midnight, sorted by start. Empty when the collection is closed that weekday
// — no entry in `opening_hours` (Python weekday() string keys, translated via
// `jsToPyWeekday`) or an empty list for it. A malformed pair is skipped
// defensively, mirroring `Collection.day_opening_blocks` on the backend —
// `opening_hours` is validated before it's ever stored, so this is a belt for
// a braces that should already be fastened, not a path this app expects to hit.
export const dayBlocks = (openingHours, date) => {
  const pyDay = jsToPyWeekday(date.getDay());
  const raw = (openingHours || {})[String(pyDay)] || [];
  return raw
    .map(([start, end]) => ({ start: parseHM(start), end: parseHM(end) }))
    .filter(({ start, end }) => Number.isFinite(start) && Number.isFinite(end))
    .sort((a, b) => a.start - b.start);
};

// The selected day's existing bookings from the thing's calendar
// (`GET /things/{code}/calendar/`), reduced to what matters for slot maths:
// `wholeDay` (a LEND/RENT or a DAY-unit RESERVE sharing the thing blocks the
// entire day, `start_time` NULL) and, otherwise, the day's booked
// `[{start, end}]` ranges in minutes. `isoDate` is the selected day.
export const dayBookings = (blockedPeriods, isoDate) => {
  const onThatDay = (blockedPeriods || []).filter(
    (b) => b.start_date <= isoDate && isoDate < b.end_date
  );
  if (onThatDay.some((b) => !b.start_time)) return { wholeDay: true, ranges: [] };
  return {
    wholeDay: false,
    ranges: onThatDay.map((b) => ({ start: parseHM(b.start_time), end: parseHM(b.end_time) })),
  };
};

const minutesRangeOverlaps = (start, end, ranges) =>
  ranges.some((r) => start < r.end && r.start < end);

// The duration choices to offer: every multiple of `minMinutes` from itself
// up to `maxMinutes` (the collection's `reservation_min_minutes`/
// `reservation_max_minutes`). The named presets this list once grew — "half
// day" and "full day" — were removed: with minute-granular
// steps the plain multiples already say the same thing in numbers. The cost
// is honest: a span crossing a gap between two blocks (the old "full day")
// is no longer offered here, though the backend still accepts one sent by
// start/end time.
//
// The `key` for a duration is the minutes themselves (`'15'`, `'90'`),
// not an hour count — the two used to coincide when every duration was a
// whole hour, but this is the value `RequestThingPage`'s label builder now
// reads directly, so recovering it via `key * 60` would be wrong the moment
// a collection's minimum isn't a whole hour.
export const durationOptions = (minMinutes, maxMinutes) => {
  const options = [];
  for (let m = minMinutes; m <= maxMinutes; m += minMinutes) {
    options.push({ key: String(m), minutes: m });
  }
  return options;
};

// The earliest a slot on `isoDate` may start, in minutes since midnight: the
// current minute when `isoDate` is today by the browser's clock, else 0. A slot
// that has already begun is not something to offer. The server refuses one too
// (`Collection.reservation_hour_violation`), by the deployment's own clock
// (`DJANGO_TIME_ZONE`, the zone `opening_hours` is written in); this uses the
// browser's, assumed to share the venue's time zone — which for an on-site
// reservation it almost always does. Both count a start in the current minute
// as not yet begun.
export const earliestStartMinutes = (isoDate, now = new Date()) =>
  isoDate === toISODate(now) ? now.getHours() * 60 + now.getMinutes() : 0;

// The valid start times ("HH:MM") for a chosen duration, stepped every
// `stepMinutes` within each opening block — the collection's `reservation_
// min_minutes`, so a short minimum genuinely offers more than one start per
// hour; a minimum lowered to 15 with a start stepped every 60 would still
// only ever offer :00 starts, making the shorter minimum useless. Every
// candidate must fit inside a single block — a span crossing one of the gaps
// between blocks is not offered (the "full day" special case that once
// allowed exactly that went with its option, 2026-09). Starts before
// `earliestStart` (`earliestStartMinutes`, above) are skipped; the step grid
// itself still runs from each block's opening, so the starts that remain
// later in the day are the same ones offered on any other day. Empty whenever
// the day is `wholeDay`-booked.
export const freeStartTimes = (
  blocks,
  durationMinutes,
  dayBookingsResult,
  stepMinutes,
  earliestStart = 0
) => {
  if (dayBookingsResult.wholeDay) return [];
  const starts = [];
  for (const block of blocks) {
    for (let cursor = block.start; cursor + durationMinutes <= block.end; cursor += stepMinutes) {
      if (cursor < earliestStart) continue;
      if (!minutesRangeOverlaps(cursor, cursor + durationMinutes, dayBookingsResult.ranges)) {
        starts.push(formatHM(cursor));
      }
    }
  }
  return starts;
};

// Disable a day in the HOUR-unit picker when it's a closure day, the
// collection is closed that weekday, or nothing on the calendar leaves even one
// free start that day (for today, counting only starts not yet passed at
// `now`). `minMinutes` is the collection's `reservation_min_minutes`.
//
// Only the **shortest** duration needs trying, not every choice
// `durationOptions` offers: any longer duration that fits at some start also
// leaves the minimum free at that same start (a sub-span, on the same grid),
// so "some duration fits" and "the minimum fits" are the same question. Asking
// it once matters because this runs for every visible calendar cell on every
// render — a 5-to-720-minute collection offers 144 durations, and on a fully
// booked day each of them used to walk the whole start grid before giving up.
export const isHourlyPickupDisabled = (
  date,
  { openingHours = {}, closedDates = [], blockedPeriods = [], minMinutes = 60, now = new Date() }
) => {
  if (isClosedDate(date, closedSet(closedDates))) return true;
  const blocks = dayBlocks(openingHours, date);
  if (!blocks.length) return true;
  const isoDate = toISODate(parseLocalDate(date));
  const bookings = dayBookings(blockedPeriods, isoDate);
  const earliest = earliestStartMinutes(isoDate, now);
  return freeStartTimes(blocks, minMinutes, bookings, minMinutes, earliest).length === 0;
};

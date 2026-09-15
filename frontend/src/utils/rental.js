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

// A booking's date/time range for a listing row — MyBookingsPage,
// OwnerBookingsPage, OwnerBookingsList — read straight off the API's own
// field names (`start_date`/`end_date` ISO dates, `start_time`/`end_time`
// 'HH:MM:SS' or absent). A whole-day booking (every LEND/RENT, every
// DAY-unit RESERVE — `start_time` unset) renders exactly as before this
// helper existed: 'DD/MM/YYYY — DD/MM/YYYY'. An HOUR-unit RESERVE_THING slot
// renders the date once plus both clock times: 'DD/MM/YYYY, HH:MM–HH:MM'.
// '' when there are no dates at all (GIFT/SELL).
export const formatBookingWhen = (booking) => {
  if (!booking?.start_date || !booking?.end_date) return '';
  const date = formatDate(booking.start_date);
  if (booking.start_time && booking.end_time) {
    return `${date}, ${booking.start_time.slice(0, 5)}–${booking.end_time.slice(0, 5)}`;
  }
  return `${date} — ${formatDate(booking.end_date)}`;
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

// Is `date` inside any blocked [start_date, end_date] period (both ends inclusive),
// OR a closure day? This is the calendar *display* range — the item is out from
// pickup through the return day. Pickup selectability uses the stricter [start, end)
// below.
export const isDateBlocked = (date, blockedPeriods, closedDates = []) => {
  const d = parseLocalDate(date);
  if (closedSet(closedDates).has(toISODate(d))) return true;
  return blockedPeriods.some((period) => {
    const start = parseLocalDate(period.start_date);
    const end = parseLocalDate(period.end_date);
    return d >= start && d <= end;
  });
};

// Is `date` blocked for a PICKUP? A booking [s, e] blocks pickup on [s, e) — but
// NOT on its return day e, which is free for the next pickup (back-to-back
// handovers, mirroring BookingPeriod.has_overlap's strict overlap).
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

// The duration choices to offer for a day's opening blocks: every multiple of
// `minMinutes` from itself up to `maxMinutes` (the collection's `reservation_
// min_minutes`/`reservation_max_minutes`), plus "half day" (the longest single
// block — only distinct from "full day" with 2+ blocks) and "full day" (the
// whole day's span, any gap included) — each offered only if it fits the
// maximum. **The maximum applies to the full-day form too, with no
// exception** (CA's call, mirroring `Collection.reservation_hour_violation`):
// a day whose total span exceeds it just doesn't offer "the whole day".
//
// The `key` for a plain duration is the minutes themselves (`'15'`, `'90'`),
// not an hour count — the two used to coincide when every duration was a
// whole hour, but this is the value `RequestThingPage`'s label builder now
// reads directly, so recovering it via `key * 60` would be wrong the moment
// a collection's minimum isn't a whole hour.
export const durationOptions = (blocks, minMinutes, maxMinutes) => {
  const options = [];
  for (let m = minMinutes; m <= maxMinutes; m += minMinutes) {
    options.push({ key: String(m), minutes: m });
  }
  if (blocks.length >= 2) {
    const longestBlock = Math.max(...blocks.map((b) => b.end - b.start));
    if (longestBlock <= maxMinutes) options.push({ key: 'halfDay', minutes: longestBlock });
  }
  if (blocks.length >= 1) {
    const fullDayMinutes = blocks[blocks.length - 1].end - blocks[0].start;
    if (fullDayMinutes <= maxMinutes) options.push({ key: 'fullDay', minutes: fullDayMinutes });
  }
  return options;
};

// The valid start times ("HH:MM") for a chosen duration, stepped every
// `stepMinutes` within each opening block — the collection's `reservation_
// min_minutes`, so a short minimum genuinely offers more than one start per
// hour; a minimum lowered to 15 with a start stepped every 60 would still
// only ever offer :00 starts, making the shorter minimum useless. "Full day"
// has exactly one candidate start — the first block's own opening time —
// accepted only if nothing already booked overlaps the whole span. Empty
// whenever the day is `wholeDay`-booked.
export const freeStartTimes = (
  blocks,
  durationMinutes,
  dayBookingsResult,
  isFullDay,
  stepMinutes
) => {
  if (dayBookingsResult.wholeDay) return [];
  if (isFullDay) {
    if (!blocks.length) return [];
    const start = blocks[0].start;
    const end = blocks[blocks.length - 1].end;
    return minutesRangeOverlaps(start, end, dayBookingsResult.ranges) ? [] : [formatHM(start)];
  }
  const starts = [];
  for (const block of blocks) {
    for (let cursor = block.start; cursor + durationMinutes <= block.end; cursor += stepMinutes) {
      if (!minutesRangeOverlaps(cursor, cursor + durationMinutes, dayBookingsResult.ranges)) {
        starts.push(formatHM(cursor));
      }
    }
  }
  return starts;
};

// Disable a day in the HOUR-unit picker when it's a closure day, the
// collection is closed that weekday, or — walking every duration choice —
// nothing on the calendar leaves even one free start that day. `minMinutes`/
// `maxMinutes` are the collection's `reservation_min_minutes`/
// `reservation_max_minutes`.
export const isHourlyPickupDisabled = (
  date,
  { openingHours = {}, closedDates = [], blockedPeriods = [], minMinutes = 60, maxMinutes = 180 }
) => {
  if (isClosedDate(date, closedSet(closedDates))) return true;
  const blocks = dayBlocks(openingHours, date);
  if (!blocks.length) return true;
  const bookings = dayBookings(blockedPeriods, toISODate(parseLocalDate(date)));
  return !durationOptions(blocks, minMinutes, maxMinutes).some(
    (opt) =>
      freeStartTimes(blocks, opt.minutes, bookings, opt.key === 'fullDay', minMinutes).length > 0
  );
};

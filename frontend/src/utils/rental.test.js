import { describe, test, expect, beforeAll, afterAll, vi } from 'vitest';
import {
  jsToPyWeekday,
  parseLocalDate,
  addDays,
  toISODate,
  weekdayAllowed,
  isDateBlocked,
  isPickupBlocked,
  isPickupDisabled,
  reservationPickupDisabled,
  derivedReturnDate,
  isoToDisplay,
  displayToIso,
  formatDate,
  formatBookingWhen,
  closedDatesToDisplay,
  parseHM,
  formatHM,
  dayBlocks,
  dayBookings,
  durationOptions,
  freeStartTimes,
  earliestStartMinutes,
  isHourlyPickupDisabled,
} from './rental';

// Run in a UTC-negative timezone so a regression to UTC date parsing
// (new Date('YYYY-MM-DD') → UTC midnight → previous local day) is actually caught.
beforeAll(() => {
  vi.stubEnv('TZ', 'America/New_York');
});
afterAll(() => {
  vi.unstubAllEnvs();
});

// Anchor: 2024-01-01 is a Monday, so 2024-01-03 is a Wednesday (Python weekday 2)
// and 2024-01-04 a Thursday (3).

describe('jsToPyWeekday', () => {
  test('maps JS Sunday-first to Python Monday-first', () => {
    expect(jsToPyWeekday(0)).toBe(6); // Sunday
    expect(jsToPyWeekday(1)).toBe(0); // Monday
    expect(jsToPyWeekday(3)).toBe(2); // Wednesday
    expect(jsToPyWeekday(6)).toBe(5); // Saturday
  });
});

describe('parseLocalDate', () => {
  test('parses a YYYY-MM-DD string on the intended LOCAL day, not UTC', () => {
    const d = parseLocalDate('2024-01-03');
    expect(d.getFullYear()).toBe(2024);
    expect(d.getMonth()).toBe(0);
    expect(d.getDate()).toBe(3); // would be 2 under the UTC-parse bug in this TZ
    expect(d.getTime()).toBe(new Date(2024, 0, 3).getTime());
  });

  test('normalises a Date to local midnight without shifting the day', () => {
    const d = parseLocalDate(new Date(2024, 0, 3, 12, 30));
    expect(d.getDate()).toBe(3);
    expect(d.getHours()).toBe(0);
  });
});

describe('addDays / toISODate / derivedReturnDate', () => {
  test('addDays keeps the return on the same weekday a week later', () => {
    // 2024-01-03 is a Wednesday; +7 days is the next Wednesday, not one short.
    expect(toISODate(addDays('2024-01-03', 7))).toBe('2024-01-10');
    expect(addDays('2024-01-03', 7).getDay()).toBe(3); // still Wednesday
  });

  test('derivedReturnDate returns pickup + length as an ISO string', () => {
    expect(derivedReturnDate('2024-01-03', 7)).toBe('2024-01-10');
    expect(derivedReturnDate('2024-01-03', '1')).toBe('2024-01-04');
  });

  test('toISODate uses local components', () => {
    expect(toISODate(new Date(2024, 0, 3))).toBe('2024-01-03');
  });
});

describe('weekdayAllowed', () => {
  test('is unrestricted when no weekdays are configured', () => {
    expect(weekdayAllowed('2024-01-04', [])).toBe(true);
  });
  test('allows only the configured Python weekdays', () => {
    expect(weekdayAllowed('2024-01-03', [2])).toBe(true); // Wednesday
    expect(weekdayAllowed('2024-01-04', [2])).toBe(false); // Thursday
  });
});

describe('isDateBlocked', () => {
  const periods = [{ start_date: '2024-01-03', end_date: '2024-01-05' }];
  test('is inclusive of both ends', () => {
    expect(isDateBlocked('2024-01-03', periods)).toBe(true);
    expect(isDateBlocked('2024-01-05', periods)).toBe(true);
  });
  test('is false outside the range', () => {
    expect(isDateBlocked('2024-01-02', periods)).toBe(false);
    expect(isDateBlocked('2024-01-06', periods)).toBe(false);
  });
  test('accepts a Date as well as a string', () => {
    expect(isDateBlocked(new Date(2024, 0, 4), periods)).toBe(true);
  });
});

describe('isPickupBlocked', () => {
  const periods = [{ start_date: '2024-01-03', end_date: '2024-01-05' }];
  test('blocks pickup on the start day and interior days', () => {
    expect(isPickupBlocked('2024-01-03', periods)).toBe(true);
    expect(isPickupBlocked('2024-01-04', periods)).toBe(true);
  });
  test('allows pickup on the return day (end) — back-to-back handover', () => {
    expect(isPickupBlocked('2024-01-05', periods)).toBe(false);
  });
  test('is false outside the range', () => {
    expect(isPickupBlocked('2024-01-02', periods)).toBe(false);
    expect(isPickupBlocked('2024-01-06', periods)).toBe(false);
  });
});

describe('isPickupDisabled', () => {
  const base = { rentalWeekdays: [2], blockedPeriods: [], duration: '' };
  test('disables a pickup on a disallowed weekday', () => {
    expect(isPickupDisabled('2024-01-04', base)).toBe(true); // Thursday
  });
  test('allows a valid pickup weekday with no duration chosen', () => {
    expect(isPickupDisabled('2024-01-03', base)).toBe(false); // Wednesday
  });
  test('allows a length whose return lands on an allowed weekday', () => {
    // Wed + 7 = next Wed, both allowed.
    expect(isPickupDisabled('2024-01-03', { ...base, duration: '7' })).toBe(false);
  });
  test('disables a length whose return lands on a disallowed weekday', () => {
    // Wed + 1 = Thursday, not allowed.
    expect(isPickupDisabled('2024-01-03', { ...base, duration: '1' })).toBe(true);
  });
  test('disables when any day in the pickup→return range is booked', () => {
    const opts = {
      rentalWeekdays: [],
      blockedPeriods: [{ start_date: '2024-01-06', end_date: '2024-01-06' }],
      duration: '7',
    };
    expect(isPickupDisabled('2024-01-03', opts)).toBe(true); // 06 falls inside [03..10]
  });
  test('allows a chained Wednesday→Wednesday pickup on an existing return day', () => {
    // Existing 7-day rental [Wed 01-03 → Wed 01-10]; a new week picked up on the
    // return day 01-10 (also a Wednesday) is now valid — strict overlap only.
    const opts = {
      rentalWeekdays: [2], // Wednesday only
      blockedPeriods: [{ start_date: '2024-01-03', end_date: '2024-01-10' }],
      duration: '7',
    };
    expect(isPickupDisabled('2024-01-10', opts)).toBe(false);
  });
  test('still disables a pickup interior to an existing booking', () => {
    const opts = {
      rentalWeekdays: [],
      blockedPeriods: [{ start_date: '2024-01-03', end_date: '2024-01-10' }],
      duration: '7',
    };
    expect(isPickupDisabled('2024-01-08', opts)).toBe(true); // 08 is interior to [03..10)
  });
  test('disables a closure day for pickup, and a length whose return lands on one', () => {
    const opts = { rentalWeekdays: [], blockedPeriods: [], closedDates: ['2024-12-25'] };
    expect(isPickupDisabled('2024-12-25', opts)).toBe(true); // pickup on the holiday
    expect(isPickupDisabled('2024-12-24', opts)).toBe(false); // interior closure is fine...
    expect(isPickupDisabled('2024-12-18', { ...opts, duration: '7' })).toBe(true); // ...but not the return
    expect(isDateBlocked('2024-12-25', [], ['2024-12-25'])).toBe(true);
  });
});

describe('reservationPickupDisabled', () => {
  test('a reservation span cannot include a closure day', () => {
    const opts = {
      rentalWeekdays: [],
      blockedPeriods: [],
      closedDates: ['2024-12-25'],
      duration: 2,
    };
    expect(reservationPickupDisabled('2024-12-24', opts)).toBe(true); // 24+25
    expect(reservationPickupDisabled('2024-12-26', opts)).toBe(false);
  });

  test('EVERY day of the span must be an allowed weekday, not just pickup and return', () => {
    // The whole reason this is a separate function from isPickupDisabled: the
    // space is occupied for the entire span, so it can't straddle a closed
    // weekday. rentalWeekdays [Mon, Wed]; a 3-day pickup on Mon 2024-01-01
    // covers Mon / Tue / Wed — the interior Tuesday is closed, even though
    // pickup (Mon) and the last day (Wed) are both fine.
    const opts = { rentalWeekdays: [0, 2], blockedPeriods: [], duration: 3 };
    expect(reservationPickupDisabled('2024-01-01', opts)).toBe(true);
    // One day only — just the Monday — is allowed.
    expect(reservationPickupDisabled('2024-01-01', { ...opts, duration: 1 })).toBe(false);
    // A span where every day lands on an allowed weekday is allowed.
    expect(
      reservationPickupDisabled('2024-01-01', { rentalWeekdays: [0, 1, 2], duration: 3 })
    ).toBe(false);
  });

  test('a span that overlaps an existing reservation is disabled', () => {
    // Mid-span day already booked → the whole pickup is off the table (the
    // reservation auto-confirms, so there is no owner step to catch a clash).
    const opts = {
      rentalWeekdays: [],
      blockedPeriods: [{ start_date: '2024-01-02', end_date: '2024-01-03' }],
      duration: 3,
    };
    expect(reservationPickupDisabled('2024-01-01', opts)).toBe(true);
    expect(reservationPickupDisabled('2024-01-01', { ...opts, blockedPeriods: [] })).toBe(false);
  });

  test('a pickup on the day an existing reservation ends is still allowed (back-to-back)', () => {
    const opts = {
      rentalWeekdays: [],
      blockedPeriods: [{ start_date: '2023-12-29', end_date: '2024-01-01' }],
      duration: 2,
    };
    expect(reservationPickupDisabled('2024-01-01', opts)).toBe(false);
  });
});

describe('closedDatesToDisplay', () => {
  test('ISO list to the comma-separated DD/MM/YYYY line', () => {
    expect(closedDatesToDisplay(['2026-12-25', '2026-12-26'])).toBe('25/12/2026, 26/12/2026');
    expect(closedDatesToDisplay([])).toBe('');
    expect(closedDatesToDisplay(undefined)).toBe('');
  });
});

describe('isoToDisplay / displayToIso', () => {
  test('round-trips a date between ISO and DD/MM/YYYY', () => {
    expect(isoToDisplay('2026-07-15')).toBe('15/07/2026');
    expect(displayToIso('15/07/2026')).toBe('2026-07-15');
    expect(displayToIso(isoToDisplay('2024-01-03'))).toBe('2024-01-03');
  });

  test('displayToIso accepts loose single-digit day/month', () => {
    expect(displayToIso('3/6/2026')).toBe('2026-06-03');
  });

  test('rejects malformed and impossible dates', () => {
    expect(isoToDisplay('')).toBe('');
    expect(isoToDisplay('15/07/2026')).toBe('');
    expect(isoToDisplay(null)).toBe('');
    expect(displayToIso('')).toBe('');
    expect(displayToIso('2026-07-15')).toBe('');
    expect(displayToIso('31/02/2026')).toBe(''); // impossible date
    expect(displayToIso('99/99/9999')).toBe('');
  });
});

describe('formatDate', () => {
  test('renders every accepted shape as DD/MM/YYYY', () => {
    expect(formatDate('2026-07-15')).toBe('15/07/2026'); // ISO date
    expect(formatDate('2026-07-15T09:30:00Z')).toBe('15/07/2026'); // ISO datetime
    expect(formatDate(new Date(2026, 6, 15))).toBe('15/07/2026'); // Date
  });

  test('pads single-digit day and month', () => {
    expect(formatDate('2026-01-05')).toBe('05/01/2026');
  });

  test("is blank — never 'Invalid Date' — for an empty or unparseable value", () => {
    expect(formatDate(null)).toBe('');
    expect(formatDate(undefined)).toBe('');
    expect(formatDate('')).toBe('');
    expect(formatDate('not a date')).toBe('');
  });
});

describe('formatBookingWhen', () => {
  test('a whole-day booking (start_time absent) renders a date range, unchanged', () => {
    expect(formatBookingWhen({ start_date: '2026-10-05', end_date: '2026-10-06' })).toBe(
      '05/10/2026 — 06/10/2026'
    );
  });

  test('an HOUR-unit reservation names the date once and both clock times', () => {
    expect(
      formatBookingWhen({
        start_date: '2026-10-05',
        end_date: '2026-10-06', // the day-based "free again" marker — must not appear
        start_time: '10:00:00',
        end_time: '13:00:00',
      })
    ).toBe('05/10/2026, 10:00–13:00');
  });

  test('is blank when there are no dates at all (GIFT/SELL)', () => {
    expect(formatBookingWhen({})).toBe('');
    expect(formatBookingWhen(null)).toBe('');
    expect(formatBookingWhen(undefined)).toBe('');
  });
});

// HOUR-unit RESERVE_THING: time-of-day helpers. CA's own example schedule —
// Mon-Thu 10:00-14:00 & 16:00-20:00, Fri 10:00-14:00, weekend closed — used
// throughout, mirroring the backend fixtures in
// core/tests/unit/test_reservation_rules.py.
// Constructed lazily (inside `beforeAll`, not here at module scope) so the
// `TZ` stub above is already active — `new Date(y, m, d)` reads local
// components at construction time, and building these before the stub runs
// would date them to whatever the real system timezone is, which then
// disagrees with every `.getDay()` read afterwards under the stubbed one.
let MON, FRI, SAT; // Monday / Friday / Saturday (see the anchor note above)
beforeAll(() => {
  MON = new Date(2024, 0, 1);
  FRI = new Date(2024, 0, 5);
  SAT = new Date(2024, 0, 6);
});
const OPENING_HOURS = {
  0: [
    ['10:00', '14:00'],
    ['16:00', '20:00'],
  ],
  1: [
    ['10:00', '14:00'],
    ['16:00', '20:00'],
  ],
  2: [
    ['10:00', '14:00'],
    ['16:00', '20:00'],
  ],
  3: [
    ['10:00', '14:00'],
    ['16:00', '20:00'],
  ],
  4: [['10:00', '14:00']],
};

describe('parseHM / formatHM', () => {
  test('round-trip "HH:MM" through minutes since midnight', () => {
    expect(parseHM('10:00')).toBe(600);
    expect(parseHM('00:00')).toBe(0);
    expect(parseHM('23:59')).toBe(1439);
    expect(formatHM(600)).toBe('10:00');
    expect(formatHM(0)).toBe('00:00');
    expect(formatHM(65)).toBe('01:05');
  });
});

describe('dayBlocks', () => {
  test('returns a weekday’s blocks sorted by start', () => {
    expect(dayBlocks(OPENING_HOURS, MON)).toEqual([
      { start: 600, end: 840 },
      { start: 960, end: 1200 },
    ]);
  });

  test('a single-block day returns exactly that block', () => {
    expect(dayBlocks(OPENING_HOURS, FRI)).toEqual([{ start: 600, end: 840 }]);
  });

  test('a day absent from opening_hours is empty (closed)', () => {
    expect(dayBlocks(OPENING_HOURS, SAT)).toEqual([]);
  });

  test('skips a malformed block instead of throwing', () => {
    expect(dayBlocks({ 0: [['not-a-time', '14:00']] }, MON)).toEqual([]);
  });
});

describe('dayBookings', () => {
  test('a day with no bookings is neither whole-day nor has any ranges', () => {
    expect(dayBookings([], '2024-01-01')).toEqual({ wholeDay: false, ranges: [] });
  });

  test('an hour-based booking on that day becomes a minutes range', () => {
    const periods = [
      { start_date: '2024-01-01', end_date: '2024-01-02', start_time: '10:00', end_time: '12:00' },
    ];
    expect(dayBookings(periods, '2024-01-01')).toEqual({
      wholeDay: false,
      ranges: [{ start: 600, end: 720 }],
    });
  });

  test('a whole-day booking (no start_time) closes the day outright', () => {
    const periods = [{ start_date: '2024-01-01', end_date: '2024-01-02', start_time: null }];
    expect(dayBookings(periods, '2024-01-01')).toEqual({ wholeDay: true, ranges: [] });
  });

  test('a booking on a different day is ignored', () => {
    const periods = [
      { start_date: '2024-01-02', end_date: '2024-01-03', start_time: '10:00', end_time: '12:00' },
    ];
    expect(dayBookings(periods, '2024-01-01')).toEqual({ wholeDay: false, ranges: [] });
  });
});

describe('durationOptions', () => {
  test('offers every multiple of the minimum up to the max, keyed by minutes', () => {
    expect(durationOptions(60, 180).map((o) => o.key)).toEqual(['60', '120', '180']);
  });

  test('offers no named presets even under a generous cap — "half day" and "full day" are gone', () => {
    // 2026-09: the presets went with the minute-granular options. A whole day
    // that fits the cap is just another plain multiple ('600'), never named.
    const keys = durationOptions(60, 720).map((o) => o.key);
    expect(keys).toEqual([
      '60',
      '120',
      '180',
      '240',
      '300',
      '360',
      '420',
      '480',
      '540',
      '600',
      '660',
      '720',
    ]);
    expect(keys.every((k) => /^\d+$/.test(k))).toBe(true);
  });

  test('a minimum shorter than an hour steps in that same short unit — the whole point of the feature', () => {
    // A minimum of 15 with a max of 45 offers three quarter-hour slots — not
    // whole hours, and not the old fixed 60-minute floor a HOUR-unit
    // collection used to be stuck with.
    expect(durationOptions(15, 45)).toEqual([
      { key: '15', minutes: 15 },
      { key: '30', minutes: 30 },
      { key: '45', minutes: 45 },
    ]);
  });

  test('a max not aligned to the minimum simply stops at the last multiple that fits', () => {
    // min 20, max 100: 20/40/60/80/100 all fit exactly (100 is itself a
    // multiple of 20); a max of 90 would stop at 80.
    expect(durationOptions(20, 90).map((o) => o.key)).toEqual(['20', '40', '60', '80']);
  });
});

describe('earliestStartMinutes', () => {
  test('today: the current minute, so nothing that already began is offered', () => {
    const now = new Date(2024, 0, 1, 12, 34, 59);
    expect(earliestStartMinutes('2024-01-01', now)).toBe(12 * 60 + 34);
  });

  test('any other day: no floor at all', () => {
    const now = new Date(2024, 0, 1, 12, 34);
    expect(earliestStartMinutes('2024-01-02', now)).toBe(0);
    expect(earliestStartMinutes('', now)).toBe(0);
  });
});

describe('freeStartTimes', () => {
  // Lazy for the same reason MON/FRI/SAT are: this describe body runs during
  // collection, before `beforeAll` stubs TZ and sets MON.
  let blocks;
  beforeAll(() => {
    blocks = dayBlocks(OPENING_HOURS, MON); // [10:00-14:00, 16:00-20:00]
  });
  const noBookings = { wholeDay: false, ranges: [] };

  test('an empty day offers every hourly slot, stepped hour by hour', () => {
    expect(freeStartTimes(blocks, 60, noBookings, 60)).toEqual([
      '10:00',
      '11:00',
      '12:00',
      '13:00',
      '16:00',
      '17:00',
      '18:00',
      '19:00',
    ]);
  });

  test('a longer duration still steps hour by hour, and stops fitting near the close', () => {
    // 10:00-14:00: 10:00 and 11:00 fit a 3h slot (12:00 would end at 15:00, past
    // close). 16:00-20:00: 16:00 and 17:00 fit (18:00 would end at 21:00).
    expect(freeStartTimes(blocks, 180, noBookings, 60)).toEqual([
      '10:00',
      '11:00',
      '16:00',
      '17:00',
    ]);
  });

  test('a shorter step offers more starts than the hour — the point of a lower minimum', () => {
    // Same 10:00-14:00 block, a 30-minute duration stepped every 15 minutes:
    // 10:00, 10:15, ..., 13:30 all fit (13:45 would end at 14:15, past close).
    expect(freeStartTimes(blocks.slice(0, 1), 30, noBookings, 15)).toEqual([
      '10:00',
      '10:15',
      '10:30',
      '10:45',
      '11:00',
      '11:15',
      '11:30',
      '11:45',
      '12:00',
      '12:15',
      '12:30',
      '12:45',
      '13:00',
      '13:15',
      '13:30',
    ]);
  });

  test('an existing booking removes only the starts that would overlap it', () => {
    const booked = { wholeDay: false, ranges: [{ start: 660, end: 780 }] }; // 11:00-13:00
    // A 1h slot at 11:00 or 12:00 overlaps the booking; 10:00 and 13:00 (touching
    // the boundary) do not — same strict-overlap rule as has_overlap.
    expect(freeStartTimes(blocks, 60, booked, 60)).toEqual([
      '10:00',
      '13:00',
      '16:00',
      '17:00',
      '18:00',
      '19:00',
    ]);
  });

  test('a whole-day booking leaves no free start at all', () => {
    expect(freeStartTimes(blocks, 60, { wholeDay: true, ranges: [] }, 60)).toEqual([]);
  });

  test('an earliest start drops the slots before it, and keeps one starting exactly then', () => {
    // 12:00 today: 10:00 and 11:00 have begun; 12:00 has not (same minute).
    expect(freeStartTimes(blocks, 60, noBookings, 60, 12 * 60)).toEqual([
      '12:00',
      '13:00',
      '16:00',
      '17:00',
      '18:00',
      '19:00',
    ]);
  });

  test('an earliest start between grid steps does not shift the grid', () => {
    // At 12:10 the next start is 13:00 — not 12:10, and not 12:15: the step
    // grid still runs from the block's opening, as on any other day.
    expect(freeStartTimes(blocks.slice(0, 1), 60, noBookings, 60, 12 * 60 + 10)).toEqual(['13:00']);
  });

  test('a duration that fits no single block offers no start — spans do not cross a gap', () => {
    // 600 minutes is the whole 10:00-20:00 day, gap included. The "full day"
    // special case (removed 2026-09) used to return the first block's opening
    // time for exactly this input; plain durations only ever start inside a
    // block they also finish inside.
    expect(freeStartTimes(blocks, 600, noBookings, 60)).toEqual([]);
  });
});

describe('isHourlyPickupDisabled', () => {
  const baseArgs = {
    openingHours: OPENING_HOURS,
    closedDates: [],
    blockedPeriods: [],
    minMinutes: 60,
    maxMinutes: 180,
  };

  test('an empty day with opening hours is selectable', () => {
    expect(isHourlyPickupDisabled(MON, baseArgs)).toBe(false);
  });

  test('a weekday absent from opening_hours is disabled', () => {
    expect(isHourlyPickupDisabled(SAT, baseArgs)).toBe(true);
  });

  test('a closed_dates entry disables the day even if it would otherwise be open', () => {
    expect(isHourlyPickupDisabled(MON, { ...baseArgs, closedDates: ['2024-01-01'] })).toBe(true);
  });

  test('a fully booked day (both blocks entirely taken) is disabled', () => {
    const blockedPeriods = [
      { start_date: '2024-01-01', end_date: '2024-01-02', start_time: '10:00', end_time: '14:00' },
      { start_date: '2024-01-01', end_date: '2024-01-02', start_time: '16:00', end_time: '20:00' },
    ];
    expect(isHourlyPickupDisabled(MON, { ...baseArgs, blockedPeriods })).toBe(true);
  });

  test('a day with at least one free hour anywhere stays selectable', () => {
    const blockedPeriods = [
      { start_date: '2024-01-01', end_date: '2024-01-02', start_time: '10:00', end_time: '14:00' },
      // the 16:00-20:00 block is untouched
    ];
    expect(isHourlyPickupDisabled(MON, { ...baseArgs, blockedPeriods })).toBe(false);
  });

  test('today, once the last start has passed, the day is disabled', () => {
    // MON's last 1h start is 19:00 (16:00-20:00 block). At 19:01 nothing is
    // left to book today; at 18:59 the 19:00 start still is.
    const late = new Date(2024, 0, 1, 19, 1);
    const stillTime = new Date(2024, 0, 1, 18, 59);
    expect(isHourlyPickupDisabled(MON, { ...baseArgs, now: late })).toBe(true);
    expect(isHourlyPickupDisabled(MON, { ...baseArgs, now: stillTime })).toBe(false);
  });

  test('the time of day only matters for today — the same clock leaves another day open', () => {
    const lateOnSunday = new Date(2023, 11, 31, 23, 30);
    expect(isHourlyPickupDisabled(MON, { ...baseArgs, now: lateOnSunday })).toBe(false);
  });

  test('a whole-day booking (start_time null) disables the day', () => {
    const blockedPeriods = [{ start_date: '2024-01-01', end_date: '2024-01-02', start_time: null }];
    expect(isHourlyPickupDisabled(MON, { ...baseArgs, blockedPeriods })).toBe(true);
  });
});

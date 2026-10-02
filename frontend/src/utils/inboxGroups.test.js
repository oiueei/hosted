import { describe, test, expect } from 'vitest';
import parity from '../test/inboxGroupParity.json';
import { isTeamBookingNotice, localToday, summarizeOwnerBookings } from './inboxGroups';

// The same table `core/tests/integration/test_inbox_group_dismiss.py` runs against
// the server's rule: whether the card folds a notice and whether the X's DELETE
// takes it must be one answer, or a notice reappears (or vanishes unseen).
describe('which notices the inbox folds into its summary card', () => {
  test('the shared table travelled intact', () => {
    expect(parity.rows.length).toBeGreaterThanOrEqual(16);
    // Both answers are in it, or the loop below could pass by always saying one.
    expect(parity.rows.some((row) => row.grouped)).toBe(true);
    expect(parity.rows.some((row) => !row.grouped)).toBe(true);
  });

  test.each(parity.rows.map((row) => [row.what, row]))('%s', (_what, row) => {
    expect(isTeamBookingNotice({ type: row.type, payload: row.payload })).toBe(row.grouped);
  });
});

describe('summarizeOwnerBookings', () => {
  const today = '2026-10-13';
  const row = (overrides) => ({
    status: 'PENDING',
    thing_type: 'LEND_THING',
    start_date: '2026-10-20',
    collection_code: 'COL001',
    ...overrides,
  });

  test('counts the requests waiting for an answer, whatever their dates', () => {
    const rows = [row(), row({ start_date: '2026-01-01' }), row({ status: 'ACCEPTED' })];

    expect(summarizeOwnerBookings(rows, { today })).toEqual({ pending: 2, upcoming: 0 });
  });

  test('a confirmed reservation counts from today on, and a past one does not', () => {
    const reserve = { thing_type: 'RESERVE_THING', status: 'ACCEPTED' };
    const rows = [
      row({ ...reserve, start_date: today }),
      row({ ...reserve, start_date: '2026-10-14' }),
      row({ ...reserve, start_date: '2026-10-12' }),
    ];

    expect(summarizeOwnerBookings(rows, { today })).toEqual({ pending: 0, upcoming: 2 });
  });

  test('a confirmed loan is neither: it is not pending and it is not a reservation', () => {
    const rows = [row({ status: 'ACCEPTED', start_date: '2026-10-20' })];

    expect(summarizeOwnerBookings(rows, { today })).toEqual({ pending: 0, upcoming: 0 });
  });

  test('on a collection’s page only that collection’s rows count', () => {
    const rows = [row(), row({ collection_code: 'COL002' }), row({ collection_code: null })];

    expect(summarizeOwnerBookings(rows, { collection: 'COL001', today }).pending).toBe(1);
    expect(summarizeOwnerBookings(rows, { today }).pending).toBe(3);
  });
});

describe('localToday', () => {
  test('is the reader’s own calendar day, zero-padded, as start_date is written', () => {
    // Late evening local time: toISOString() would already say tomorrow in a
    // zone ahead of UTC, which is the mistake this reads around.
    expect(localToday(new Date(2026, 0, 5, 23, 59))).toBe('2026-01-05');
    expect(localToday(new Date(2026, 9, 13, 0, 1))).toBe('2026-10-13');
  });
});

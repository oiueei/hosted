/**
 * The inbox folds a manager's request and reservation notices into one summary
 * card once there are more than a few of them (`InboxNotifications`), and the
 * card's X dismisses them all with one call
 * (`DELETE /api/v1/inbox/?group=bookings`).
 *
 * `isTeamBookingNotice` is the browser's copy of the server's rule —
 * `InAppNotification.team_booking_notices` in `core/models/notification.py` —
 * and the two must agree on every notice: a card that folded one the server
 * then kept would bring it back on the next load, and one the server deleted
 * but the card never showed would vanish unseen. `test/inboxGroupParity.json`
 * holds them together (this file's test and
 * `core/tests/integration/test_inbox_group_dismiss.py` both run it). The rule
 * is who the copy is *for*: the notices that go to whoever manages a request or
 * reservation are in; a copy for the person who asked, or who held the
 * reservation, is out — the card links to the team's page, which is not theirs.
 */
export const GROUP_THRESHOLD = 3;

const TEAM_TYPES = new Set(['BOOKING_REQUESTED', 'BOOKING_DECIDED', 'RESERVATION_MADE']);

export function isTeamBookingNotice(notification) {
  const { type } = notification;
  if (TEAM_TYPES.has(type)) return true;
  if (type !== 'RESERVATION_CANCELLED') return false;
  const payload = notification.payload || {};
  // Told to a manager who didn't cancel, or a manager's own record of cancelling
  // somebody else's (it names the member, empty or not — the key is the signal).
  // The member's copies (`cancelled_by_owner: true`, their own record with no
  // `member_name`) and anything older than the key stay where they are.
  if (payload.cancelled_by_owner === false) return true;
  return payload.by_you === true && 'member_name' in payload;
}

/** Today as `YYYY-MM-DD` in the reader's own time zone, the way `start_date` is written. */
export function localToday(now = new Date()) {
  const pad = (n) => String(n).padStart(2, '0');
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

/**
 * The two figures on the summary card, from `GET /api/v1/owner-bookings/` rows:
 * requests still waiting for an answer, and reservations still to come. A
 * reservation confirms itself and is never pending, so without the second figure
 * a reservations group would read "0" for good. On a collection's own page only
 * that collection's rows count.
 */
export function summarizeOwnerBookings(rows, { collection, today }) {
  let pending = 0;
  let upcoming = 0;
  for (const booking of rows) {
    if (collection && booking.collection_code !== collection) continue;
    if (booking.status === 'PENDING') {
      pending += 1;
    } else if (
      booking.thing_type === 'RESERVE_THING' &&
      booking.status === 'ACCEPTED' &&
      booking.start_date &&
      booking.start_date >= today
    ) {
      upcoming += 1;
    }
  }
  return { pending, upcoming };
}

import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { describe, test, expect, vi, beforeEach, afterEach } from 'vitest';
import { axe, toHaveNoViolations } from 'jest-axe';
import MyBookingsPage from './MyBookingsPage';

expect.extend(toHaveNoViolations);

// The JSON shape `/api/v1/my-bookings/` returns (the subset the page reads).
const booking = (over = {}) => ({
  code: 'BKG001',
  status: 'PENDING',
  thing_code: 'THG001',
  thing_headline: 'Cordless drill',
  thing_type: 'LEND_THING',
  owner_name: 'Lala',
  start_date: '2026-09-01',
  end_date: '2026-09-08',
  created: '2026-08-01T10:00:00Z',
  ...over,
});

function mockList(results, next = null) {
  globalThis.fetch = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({ results, next }),
  });
}

function renderPage() {
  return render(
    <MemoryRouter>
      <MyBookingsPage />
    </MemoryRouter>
  );
}

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem('userCode', 'USR001');
});
afterEach(() => {
  vi.restoreAllMocks();
});

describe('MyBookingsPage listing', () => {
  test('splits pending requests from settled ones', async () => {
    // The split is the page's whole organising idea: what still needs the
    // owner's answer is actionable, everything else is history.
    mockList([
      booking({ code: 'BKG001', status: 'PENDING', thing_headline: 'Cordless drill' }),
      booking({ code: 'BKG002', status: 'ACCEPTED', thing_headline: 'Tent' }),
    ]);
    renderPage();

    await screen.findByText('Cordless drill');
    expect(screen.getByRole('heading', { name: 'Pending' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Past requests' })).toBeInTheDocument();
    expect(screen.getByText('Tent')).toBeInTheDocument();
  });

  test('both tables carry a name, so they can be told apart in a rotor', async () => {
    // A <table> with no <caption> is announced as "table, 2 columns" and nothing
    // else. This page has two of them, one under each heading — and a heading is
    // not a table's name, so a reader listing the tables on this page got two
    // identical nameless entries. The captions are screen-reader-only: the
    // headings already say it on screen.
    renderPage();

    expect(
      await screen.findByRole('table', { name: 'Requests waiting for an answer' })
    ).toBeInTheDocument();
    expect(screen.getByRole('table', { name: 'Requests already closed' })).toBeInTheDocument();
  });

  test('the column holding the cancel control has a name a screen reader can say', async () => {
    // It was an empty <th> (axe empty-table-header): moving through the row, a
    // reader reached the cancel control under a column with no name at all.
    mockList([booking()]);
    renderPage();

    await screen.findByText('Cordless drill');
    expect(screen.getAllByRole('columnheader', { name: 'Actions' }).length).toBeGreaterThan(0);
    expect(screen.queryByRole('columnheader', { name: '' })).not.toBeInTheDocument();
  });

  test('with nothing pending, the section says so instead of vanishing', async () => {
    // An empty pending table would read as "the page is broken", not "you have
    // no open requests".
    mockList([booking({ status: 'REJECTED', thing_headline: 'Tent' })]);
    renderPage();

    await screen.findByText('Tent');
    expect(screen.getByText('No pending requests.')).toBeInTheDocument();
  });

  test('each status carries its own semantic label', async () => {
    mockList([
      booking({ code: 'B1', status: 'PENDING' }),
      booking({ code: 'B2', status: 'ACCEPTED' }),
      booking({ code: 'B3', status: 'REJECTED' }),
      booking({ code: 'B4', status: 'CANCELLED' }),
      booking({ code: 'B5', status: 'EXPIRED' }),
    ]);
    renderPage();

    await screen.findByText('Confirmed');
    expect(screen.getByText('Rejected')).toBeInTheDocument();
    expect(screen.getByText('Cancelled')).toBeInTheDocument();
    expect(screen.getByText('Expired')).toBeInTheDocument();
    // An expired request is the one status a user cannot explain to themselves,
    // so it must say why it lapsed.
    expect(screen.getByText(/expired automatically/)).toBeInTheDocument();
  });

  test('a booking with no dates shows the placeholder, not "Invalid Date"', async () => {
    // GIFT/SELL holds carry no range; formatting null through toLocaleDateString
    // would print "Invalid Date" into the table.
    mockList([booking({ start_date: null, end_date: null, thing_type: 'GIFT_THING' })]);
    renderPage();

    await screen.findByText('Cordless drill');
    expect(screen.queryByText(/Invalid Date/)).not.toBeInTheDocument();
  });

  test('dates render DD/MM/YYYY, matching the picker — not ISO, not US order', async () => {
    mockList([booking({ start_date: '2026-09-01', end_date: '2026-09-08' })]);
    renderPage();

    await screen.findByText('Cordless drill');
    expect(screen.getByText(/01\/09\/2026\s*—\s*08\/09\/2026/)).toBeInTheDocument();
    expect(screen.queryByText(/2026-09-01/)).not.toBeInTheDocument();
    expect(screen.queryByText(/9\/1\/2026/)).not.toBeInTheDocument();
  });

  test('an HOUR-unit reservation shows the date once and both clock times', async () => {
    mockList([
      booking({
        thing_type: 'RESERVE_THING',
        status: 'ACCEPTED',
        start_date: '2026-09-01',
        end_date: '2026-09-02', // the day-based "free again" marker — must not show
        start_time: '11:00:00',
        end_time: '13:00:00',
      }),
    ]);
    renderPage();

    await screen.findByText('Cordless drill');
    expect(screen.getByText(/01\/09\/2026, 11:00–13:00/)).toBeInTheDocument();
    expect(screen.queryByText(/02\/09\/2026/)).not.toBeInTheDocument();
  });

  test('a one-day reservation lists as one day, not up to the day the space frees up', async () => {
    mockList([
      booking({
        thing_type: 'RESERVE_THING',
        status: 'ACCEPTED',
        start_date: '2026-09-01',
        end_date: '2026-09-02', // start + 1 day: free again on the 2nd
      }),
    ]);
    renderPage();

    await screen.findByText('Cordless drill');
    expect(screen.getByText('01/09/2026')).toBeInTheDocument();
    expect(screen.queryByText(/02\/09\/2026/)).not.toBeInTheDocument();
  });

  test('the thing links to its page and names the owner', async () => {
    mockList([booking()]);
    renderPage();

    const link = await screen.findByRole('link', { name: 'Cordless drill' });
    expect(link).toHaveAttribute('href', '/things/THG001');
    expect(screen.getByText('Lala')).toBeInTheDocument();
  });

  test('an empty list offers a way out rather than a dead end', async () => {
    mockList([]);
    renderPage();

    await screen.findByText('You have no booking requests yet.');
    expect(screen.getByRole('link', { name: 'Browse collections' })).toHaveAttribute('href', '/');
  });

  test('a failed load says so instead of spinning forever', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      json: async () => ({}),
    });
    renderPage();

    expect(await screen.findByText('Error loading bookings.')).toBeInTheDocument();
  });
});

describe('MyBookingsPage cancelling', () => {
  test('only a pending request offers the cancel control', async () => {
    // Cancelling a settled request is meaningless, and offering it would invite
    // an error the user cannot undo.
    mockList([booking({ code: 'B1', status: 'ACCEPTED' })]);
    renderPage();

    await screen.findByText('Confirmed');
    expect(
      screen.queryByRole('button', { name: 'Cancel this booking request' })
    ).not.toBeInTheDocument();
  });

  test('cancelling posts to the booking and moves the row to Cancelled', async () => {
    globalThis.fetch = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ results: [booking()] }),
      })
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({}) });
    renderPage();

    fireEvent.click(await screen.findByRole('button', { name: 'Cancel this booking request' }));

    await screen.findByText('Cancelled');
    const [url, options] = globalThis.fetch.mock.calls[1];
    expect(url).toBe('/api/v1/bookings/BKG001/cancel/');
    expect(options.method).toBe('POST');
    // The row must leave the pending section, not merely relabel in place.
    expect(screen.getByText('No pending requests.')).toBeInTheDocument();
    expect(screen.getByText('Request cancelled.')).toBeInTheDocument();
  });

  test('a rejected cancel leaves the request pending and says so', async () => {
    // The dangerous failure is a request that *looks* cancelled but is not: the
    // owner still holds it, and the user stops waiting for an answer.
    globalThis.fetch = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ results: [booking()] }),
      })
      .mockResolvedValueOnce({ ok: false, status: 400, json: async () => ({}) });
    renderPage();

    fireEvent.click(await screen.findByRole('button', { name: 'Cancel this booking request' }));

    expect(await screen.findByText('Error cancelling request.')).toBeInTheDocument();
    expect(screen.queryByText('Cancelled')).not.toBeInTheDocument();
    expect(screen.queryByText('No pending requests.')).not.toBeInTheDocument();
    // Still cancellable — the user has to be able to try again.
    expect(screen.getByRole('button', { name: 'Cancel this booking request' })).toBeInTheDocument();
  });
});

/**
 * A reservation auto-confirms, so cancelling one tells the group, frees the slot
 * for anybody else, and cannot be undone. It used to go on one press of an icon
 * in a table row; now the press asks first, naming what would go. (Withdrawing a
 * *pending* request stays one press — pinned by the block above, whose POST is
 * the very next call after the click.)
 */
describe('MyBookingsPage cancelling a confirmed reservation', () => {
  const reservation = booking({
    thing_type: 'RESERVE_THING',
    thing_headline: 'Laser cutter',
    status: 'ACCEPTED',
    start_date: '2099-01-10',
    end_date: '2099-01-11',
    start_time: '10:00:00',
    end_time: '11:30:00',
  });
  const posts = () => globalThis.fetch.mock.calls.filter(([, o]) => o?.method === 'POST');

  beforeEach(() => {
    globalThis.fetch = vi.fn((url, opts) =>
      Promise.resolve(
        opts?.method === 'POST'
          ? { ok: true, status: 200, json: async () => ({}) }
          : { ok: true, status: 200, json: async () => ({ results: [reservation] }) }
      )
    );
  });

  test('one press asks first, names what would go, and sends nothing', async () => {
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Cancel reservation' }));

    const dialog = await screen.findByRole('dialog', { name: 'Cancel this reservation?' });
    expect(dialog).toHaveTextContent('Laser cutter — 10/01/2099, 10:00–11:30');
    expect(dialog).toHaveTextContent(/can't be undone/);
    expect(posts()).toHaveLength(0);
    // Scoped to the dialog, which is what this adds. `region` is off: the render
    // has no app landmarks to hold it (as in a11yInteractive.test.jsx).
    expect(await axe(dialog, { rules: { region: { enabled: false } } })).toHaveNoViolations();
  });

  test('confirming cancels it, once, and says it was the reservation', async () => {
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Cancel reservation' }));
    const dialog = await screen.findByRole('dialog');

    fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel reservation' }));

    expect(await screen.findByText('Reservation cancelled.')).toBeInTheDocument();
    expect(posts().map(([u]) => u)).toEqual(['/api/v1/bookings/BKG001/cancel/']);
    expect(screen.getByText('Cancelled')).toBeInTheDocument();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  test('backing out leaves the reservation standing', async () => {
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Cancel reservation' }));
    const dialog = await screen.findByRole('dialog');

    // Its way out is "Back": a "Cancel" beside "Cancel reservation" would read
    // as the same action.
    expect(within(dialog).queryByRole('button', { name: 'Cancel' })).not.toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole('button', { name: 'Back' }));

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(posts()).toHaveLength(0);
    expect(screen.getByText('Confirmed')).toBeInTheDocument();
  });
});

describe('MyBookingsPage pagination', () => {
  test('"Load more" appends the next page and keeps the request same-origin', async () => {
    // DRF returns an absolute `next`; sending it verbatim would leave the Vite
    // proxy in dev and drop the auth cookies with it.
    globalThis.fetch = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({
          results: [booking({ code: 'B1', thing_headline: 'Cordless drill' })],
          next: 'http://testserver/api/v1/my-bookings/?page=2',
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({
          results: [booking({ code: 'B2', thing_headline: 'Tent' })],
          next: null,
        }),
      });
    renderPage();

    fireEvent.click(await screen.findByRole('button', { name: 'Load more' }));

    await screen.findByText('Tent');
    expect(globalThis.fetch.mock.calls[1][0]).toBe('/api/v1/my-bookings/?page=2');
    // Appended, not replaced.
    expect(screen.getByText('Cordless drill')).toBeInTheDocument();
    // Exhausted: the button must go, or it re-fetches the same page forever.
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: 'Load more' })).not.toBeInTheDocument()
    );
  });

  test('a refused second page says so and keeps the first one on screen', async () => {
    // Regression: `!res.ok` had no branch. The button re-enabled, nothing
    // appeared and nothing said why — which reads as a broken app rather than
    // a failed request.
    globalThis.fetch = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({
          results: [booking({ code: 'B1', thing_headline: 'Cordless drill' })],
          next: 'http://testserver/api/v1/my-bookings/?page=2',
        }),
      })
      .mockResolvedValueOnce({ ok: false, status: 500, json: async () => ({}) });
    renderPage();

    fireEvent.click(await screen.findByRole('button', { name: 'Load more' }));

    expect(await screen.findByText(/couldn't load more/i)).toBeInTheDocument();
    expect(screen.getByText('Cordless drill')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Load more' })).toBeEnabled();
  });

  test('no "Load more" when the first page is the only page', async () => {
    mockList([booking()], null);
    renderPage();

    await screen.findByText('Cordless drill');
    expect(screen.queryByRole('button', { name: 'Load more' })).not.toBeInTheDocument();
  });
});

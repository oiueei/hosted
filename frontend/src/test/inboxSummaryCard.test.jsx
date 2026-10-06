import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { vi, describe, test, expect, beforeEach, afterEach } from 'vitest';

window.scrollTo = vi.fn();

vi.mock('../services/api', () => ({
  apiFetch: vi.fn(),
  getCsrfToken: vi.fn(() => 'mock-csrf'),
}));

import { apiFetch } from '../services/api';
import i18n from '../i18n';
import InboxNotifications from '../components/InboxNotifications';

/**
 * Past three notices about requests and reservations — the ones that go to whoever
 * manages them — the inbox shows one card with the real figures instead of a card
 * per event (the inbox filled too
 * fast for the first early adopters). The figures are the requests still waiting and the reservations still to
 * come, read from the owner-bookings list; never a count of notices, which would
 * say "5 pending" with four of them already confirmed.
 */

const ok = (body) => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });

// A day relative to today, as the reader's calendar writes it.
const day = (offset) => {
  const d = new Date();
  d.setDate(d.getDate() + offset);
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
};

const requested = (n, collection = 'COL001') => ({
  code: `REQ${n}`,
  type: 'BOOKING_REQUESTED',
  payload: {
    thing_headline: `Thing ${n}`,
    requester_name: 'Lili',
    booking_code: `BKG${n}`,
    thing_code: `THG${n}`,
    collection_code: collection,
  },
  created: '2026-10-02T10:00:00Z',
});

const madeReservation = (n) => ({
  code: `MAD${n}`,
  type: 'RESERVATION_MADE',
  payload: {
    thing_headline: `Room ${n}`,
    requester_name: 'Lili',
    start_date: day(3),
    end_date: day(4),
    start_time: null,
    end_time: null,
    booking_code: `BKR${n}`,
    thing_code: `ROOM${n}`,
    collection_code: 'COL001',
  },
  created: '2026-10-02T10:00:00Z',
});

const faqQuestion = {
  code: 'FAQ001',
  type: 'FAQ_QUESTION',
  payload: {
    thing_headline: 'A ladder',
    questioner_name: 'Lili',
    thing_code: 'THG099',
    collection_code: 'COL001',
  },
  created: '2026-10-02T09:00:00Z',
};

// A copy for the member whose reservation a manager cancelled: hers, not the team's.
const cancelledForTheMember = {
  code: 'CNC001',
  type: 'RESERVATION_CANCELLED',
  payload: {
    thing_headline: 'Room 9',
    other_name: 'Lala',
    start_date: day(3),
    end_date: day(4),
    start_time: null,
    end_time: null,
    thing_code: 'ROOM09',
    cancelled_by_owner: true,
  },
  created: '2026-10-02T09:00:00Z',
};

const booking = (overrides) => ({
  status: 'PENDING',
  thing_type: 'LEND_THING',
  start_date: day(5),
  collection_code: 'COL001',
  ...overrides,
});
const reservation = (overrides) =>
  booking({ thing_type: 'RESERVE_THING', status: 'ACCEPTED', ...overrides });

const FOUR = [requested(1), requested(2), requested(3), requested(4)];

/** The API as the inbox sees it: its list, and the owner's bookings in pages. */
function setApi({ inbox = FOUR, pages = [[]], failFigures = false, hold } = {}) {
  apiFetch.mockImplementation((url, options) => {
    if (options?.method === 'DELETE') return ok(null);
    if (url.startsWith('/api/v1/owner-bookings/')) {
      if (hold) return hold;
      if (failFigures) return Promise.resolve({ ok: false, status: 500 });
      const page = Number(new URL(url, 'http://x').searchParams.get('page') || 1);
      const next =
        page < pages.length
          ? `http://testserver/api/v1/owner-bookings/?page=${page + 1}&page_size=100`
          : null;
      return ok({ results: pages[page - 1], next });
    }
    return ok(inbox);
  });
}

const renderInbox = (props) =>
  render(
    <MemoryRouter>
      <InboxNotifications {...props} />
    </MemoryRouter>
  );

const ownerBookingsCalls = () =>
  apiFetch.mock.calls.filter(([url]) => url.startsWith('/api/v1/owner-bookings/'));

beforeEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
});
afterEach(async () => {
  await i18n.changeLanguage('en');
  localStorage.removeItem('i18nextLng');
});

describe('three or fewer: the inbox is as it was', () => {
  test('three team notices stay three cards, and the figures are never asked for', async () => {
    setApi({ inbox: [requested(1), requested(2), requested(3)] });

    renderInbox();

    expect(await screen.findByText(/Thing 3/)).toBeInTheDocument();
    expect(screen.getByText(/Thing 1/)).toBeInTheDocument();
    expect(screen.queryByText('Requests and reservations')).not.toBeInTheDocument();
    expect(ownerBookingsCalls()).toHaveLength(0);
  });

  test('a copy for the member does not count towards the fold: it stays a card of its own', async () => {
    setApi({ inbox: [requested(1), requested(2), requested(3), cancelledForTheMember] });

    renderInbox();

    // Three that are the team's, plus hers: no fold, all four visible, and the
    // summary's link to the team's page never offered for a notice that isn't theirs.
    expect(await screen.findByText(/Room 9/)).toBeInTheDocument();
    expect(screen.getByText(/Thing 1/)).toBeInTheDocument();
    expect(screen.queryByText('Requests and reservations')).not.toBeInTheDocument();
    expect(ownerBookingsCalls()).toHaveLength(0);
  });
});

describe('more than three: one card with the real figures', () => {
  test('replaces them with the requests waiting and the reservations still to come', async () => {
    setApi({
      inbox: [requested(1), requested(2), madeReservation(1), madeReservation(2)],
      pages: [
        [
          booking(),
          booking(),
          booking({ status: 'ACCEPTED' }), // a confirmed loan: neither
          reservation(), // still to come
          reservation({ start_date: day(-2) }), // already past: not counted
          booking({ status: 'REJECTED' }),
        ],
      ],
    });

    renderInbox();

    expect(
      await screen.findByText('You have 2 pending requests and 1 upcoming reservation.')
    ).toBeInTheDocument();
    expect(screen.getByText('Requests and reservations')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'See them all' })).toHaveAttribute(
      'href',
      '/owner-bookings'
    );
    // The four notices it stands for are gone from the page.
    expect(screen.queryByText(/Thing 1/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Room 2/)).not.toBeInTheDocument();
  });

  test('says singular for one', async () => {
    setApi({ pages: [[booking()]] });

    renderInbox();

    expect(await screen.findByText('You have 1 pending request.')).toBeInTheDocument();
  });

  test('both at zero says so, not "0 pending requests"', async () => {
    setApi({ pages: [[booking({ status: 'ACCEPTED' })]] });

    renderInbox();

    expect(await screen.findByText('You have nothing pending.')).toBeInTheDocument();
    expect(screen.queryByText(/0 /)).not.toBeInTheDocument();
  });

  test('on a collection’s page only that collection’s rows count', async () => {
    setApi({
      pages: [
        [booking(), booking({ collection_code: 'COL002' }), booking({ collection_code: 'COL003' })],
      ],
    });

    renderInbox({ collection: 'COL001' });

    expect(await screen.findByText('You have 1 pending request.')).toBeInTheDocument();
    expect(apiFetch).toHaveBeenCalledWith('/api/v1/inbox/?collection=COL001', expect.anything());
  });

  test('a notice of another kind stays loose beside the card', async () => {
    setApi({ inbox: [...FOUR, faqQuestion], pages: [[booking()]] });

    renderInbox();

    expect(await screen.findByText('Requests and reservations')).toBeInTheDocument();
    expect(screen.getByText(/A ladder/)).toBeInTheDocument();
  });

  test('counts the whole list, following the API’s pages', async () => {
    setApi({ pages: [[booking()], [booking(), booking()]] });

    renderInbox();

    expect(await screen.findByText('You have 3 pending requests.')).toBeInTheDocument();
    expect(ownerBookingsCalls().map(([url]) => url)).toEqual([
      '/api/v1/owner-bookings/?page_size=100',
      '/api/v1/owner-bookings/?page=2&page_size=100',
    ]);
  });
});

describe('when the figures are not there', () => {
  test('while they load the card is its label and its link, with no body', async () => {
    let release;
    const hold = new Promise((resolve) => {
      release = resolve;
    });
    setApi({ hold });

    renderInbox();

    expect(await screen.findByText('Requests and reservations')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'See them all' })).toBeInTheDocument();
    expect(screen.queryByText(/You have/)).not.toBeInTheDocument();

    release({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ results: [booking()], next: null }),
    });
    expect(await screen.findByText('You have 1 pending request.')).toBeInTheDocument();
  });

  test('if they cannot be read the link is enough: never an invented zero', async () => {
    setApi({ failFigures: true });

    renderInbox();

    expect(await screen.findByText('Requests and reservations')).toBeInTheDocument();
    await waitFor(() => expect(ownerBookingsCalls().length).toBeGreaterThan(0));
    expect(screen.getByRole('link', { name: 'See them all' })).toBeInTheDocument();
    expect(screen.queryByText(/You have/)).not.toBeInTheDocument();
  });

  test('a list longer than it will count gives no number rather than a short one', async () => {
    // Every page says there is another one.
    apiFetch.mockImplementation((url, options) => {
      if (options?.method === 'DELETE') return ok(null);
      if (url.startsWith('/api/v1/owner-bookings/')) {
        return ok({
          results: [booking()],
          next: 'http://testserver/api/v1/owner-bookings/?page=2',
        });
      }
      return ok(FOUR);
    });

    renderInbox();

    expect(await screen.findByText('Requests and reservations')).toBeInTheDocument();
    await waitFor(() => expect(ownerBookingsCalls()).toHaveLength(10));
    expect(screen.queryByText(/You have/)).not.toBeInTheDocument();
  });
});

describe('the X on the card', () => {
  test('dismisses every notice it stands for in one call, and the card goes', async () => {
    setApi({ inbox: [...FOUR, faqQuestion], pages: [[booking()]] });
    renderInbox();
    await screen.findByText('You have 1 pending request.');

    // The card is first; the loose notice after it has its own X.
    fireEvent.click(screen.getAllByRole('button', { name: 'Dismiss' })[0]);

    await waitFor(() =>
      expect(screen.queryByText('Requests and reservations')).not.toBeInTheDocument()
    );
    expect(apiFetch).toHaveBeenCalledWith('/api/v1/inbox/?group=bookings', { method: 'DELETE' });
    // Not one call per notice, and not the loose one.
    expect(apiFetch.mock.calls.filter(([, o]) => o?.method === 'DELETE')).toHaveLength(1);
    expect(screen.getByText(/A ladder/)).toBeInTheDocument();
  });

  test('on a collection’s page it asks for that collection only', async () => {
    setApi({ pages: [[booking()]] });
    renderInbox({ collection: 'COL001' });
    await screen.findByText('You have 1 pending request.');

    fireEvent.click(screen.getByRole('button', { name: 'Dismiss' }));

    await waitFor(() =>
      expect(apiFetch).toHaveBeenCalledWith('/api/v1/inbox/?group=bookings&collection=COL001', {
        method: 'DELETE',
      })
    );
  });
});

describe('in the reader’s language', () => {
  test.each([
    ['es', 'Tienes 2 solicitudes pendientes y 1 reserva próxima.', 'Solicitudes y reservas'],
    ['ca', 'Tens 2 sol·licituds pendents i 1 reserva propera.', 'Sol·licituds i reserves'],
  ])('%s joins the two figures with its own "and"', async (language, sentence, label) => {
    await i18n.changeLanguage(language);
    setApi({ pages: [[booking(), booking(), reservation()]] });

    renderInbox();

    expect(await screen.findByText(sentence)).toBeInTheDocument();
    expect(screen.getByText(label)).toBeInTheDocument();
  });
});

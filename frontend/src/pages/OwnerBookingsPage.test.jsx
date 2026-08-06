import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, test, expect, vi, beforeEach, afterEach } from 'vitest';

vi.mock('../services/api', () => ({
  apiFetch: vi.fn(),
  getCsrfToken: () => 'tok',
  extractApiError: () => null,
}));

import { apiFetch } from '../services/api';
import OwnerBookingsPage from './OwnerBookingsPage';

// The owner's mirror of /my-bookings, and the page that closed a real asymmetry:
// a requester has always had a list, while an owner had only the email, an inbox
// banner, or opening each collection in turn. `transferConfirm.test.jsx` covers
// the one path that needs a dialogue (accepting a gift hands it over for good);
// this file covers the rest of the page — deciding, the empty states, a failed
// load, and the pager — the same ground MyBookingsPage.test.jsx holds for the
// other side of the same booking.

// The JSON shape `/api/v1/owner-bookings/` returns (the subset the page reads).
const booking = (over = {}) => ({
  code: 'BKG001',
  status: 'PENDING',
  thing_code: 'THG001',
  thing_headline: 'Cordless drill',
  thing_type: 'LEND_THING',
  thing_is_endless: false,
  requester_name: 'Lele',
  start_date: '2026-09-01',
  end_date: '2026-09-08',
  created: '2026-08-01T10:00:00Z',
  ...over,
});

/** GETs return `pages` in order; POSTs answer with `postOk`. */
function mockApi(pages, { postOk = true } = {}) {
  let page = 0;
  apiFetch.mockImplementation((url, opts) => {
    if (opts?.method === 'POST') {
      return Promise.resolve({ ok: postOk, status: postOk ? 200 : 400, json: async () => ({}) });
    }
    const body = pages[Math.min(page, pages.length - 1)];
    page += 1;
    return Promise.resolve({ ok: true, status: 200, json: async () => body });
  });
}

const renderPage = () => render(<MemoryRouter><OwnerBookingsPage /></MemoryRouter>);

const postUrls = () =>
  apiFetch.mock.calls.filter(([, o]) => o?.method === 'POST').map(([u]) => u);

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem('userCode', 'USR001');
  vi.clearAllMocks();
});
afterEach(() => vi.restoreAllMocks());

describe('OwnerBookingsPage listing', () => {
  test('names who is waiting and on what, and splits pending from settled', async () => {
    mockApi([{
      results: [
        booking(),
        booking({ code: 'BKG002', status: 'ACCEPTED', thing_headline: 'Ladder', requester_name: 'Lili' }),
      ],
      next: null,
    }]);
    renderPage();

    // The column an owner needs that the requester's page doesn't have: who asked.
    expect(await screen.findByText('Asked by Lele')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Cordless drill' })).toHaveAttribute(
      'href',
      '/things/THG001'
    );
    expect(screen.getByRole('heading', { name: 'Waiting on you' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Past requests' })).toBeInTheDocument();
  });

  test('with nothing pending, the section says so rather than vanishing', async () => {
    mockApi([{ results: [booking({ status: 'REJECTED' })], next: null }]);
    renderPage();

    expect(await screen.findByText('Nothing waiting on you right now.')).toBeInTheDocument();
    // "Past requests" still renders, so the settled row isn't orphaned.
    expect(screen.getByRole('heading', { name: 'Past requests' })).toBeInTheDocument();
  });

  test('an owner nobody has asked gets a way out, not a blank page', async () => {
    mockApi([{ results: [], next: null }]);
    renderPage();

    expect(await screen.findByText('Nobody has requested anything from you yet.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Browse collections' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Waiting on you' })).toBeNull();
  });

  test('a failed load says so instead of spinning forever', async () => {
    apiFetch.mockResolvedValue({ ok: false, status: 500, json: async () => ({}) });
    renderPage();

    expect(await screen.findByText('Error loading requests.')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Waiting on you' })).toBeNull();
  });

  test('a dropped connection is reported, not swallowed into a spinner', async () => {
    apiFetch.mockRejectedValue(new Error('offline'));
    renderPage();

    expect(await screen.findByText('Connection error.')).toBeInTheDocument();
  });
});

describe('OwnerBookingsPage deciding', () => {
  // Rejecting is the half `transferConfirm.test.jsx` never touches, and it is
  // the one an owner reaches for most: it never transfers anything, so it must
  // commit on the first click with no dialogue in the way.
  test('rejecting posts once and moves the row out of the pending list', async () => {
    mockApi([{ results: [booking()], next: null }]);
    renderPage();
    await screen.findByRole('link', { name: 'Cordless drill' });

    fireEvent.click(screen.getByRole('button', { name: 'Decline this request' }));

    await waitFor(() =>
      expect(postUrls()).toEqual(['/api/v1/bookings/BKG001/reject/'])
    );
    expect(screen.queryByRole('dialog')).toBeNull();
    // The decision is reflected without a refetch, and the row leaves "Waiting
    // on you" — an answered request must stop looking like a question.
    expect(await screen.findByText('Rejected')).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByText('Nothing waiting on you right now.')).toBeInTheDocument()
    );
  });

  test('accepting a loan commits straight away — it comes back', async () => {
    mockApi([{ results: [booking()], next: null }]);
    renderPage();
    await screen.findByRole('link', { name: 'Cordless drill' });

    fireEvent.click(screen.getByRole('button', { name: 'Confirm this request' }));

    await waitFor(() => expect(postUrls()).toEqual(['/api/v1/bookings/BKG001/accept/']));
    expect(await screen.findByText('Confirmed')).toBeInTheDocument();
  });

  test('a refused decision leaves the request pending and says so', async () => {
    mockApi([{ results: [booking()], next: null }], { postOk: false });
    renderPage();
    await screen.findByRole('link', { name: 'Cordless drill' });

    fireEvent.click(screen.getByRole('button', { name: 'Decline this request' }));

    expect(await screen.findByText(/Couldn't answer that request/i)).toBeInTheDocument();
    // The optimistic update must not run on a failure: the owner has to be able
    // to see the request is still unanswered and try again.
    expect(screen.getByText('Pending')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Decline this request' })).toBeInTheDocument();
  });

  test('a settled request offers no decision controls at all', async () => {
    mockApi([{ results: [booking({ status: 'ACCEPTED' })], next: null }]);
    renderPage();
    await screen.findByRole('link', { name: 'Cordless drill' });

    expect(screen.queryByRole('button', { name: 'Confirm this request' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Decline this request' })).toBeNull();
  });
});

describe('OwnerBookingsPage pagination', () => {
  test('"Load more" appends the next page and keeps the request same-origin', async () => {
    mockApi([
      { results: [booking()], next: 'http://api.example.com/api/v1/owner-bookings/?page=2' },
      { results: [booking({ code: 'BKG002', thing_headline: 'Ladder' })], next: null },
    ]);
    renderPage();
    await screen.findByRole('link', { name: 'Cordless drill' });

    fireEvent.click(screen.getByRole('button', { name: 'Load more' }));

    expect(await screen.findByRole('link', { name: 'Ladder' })).toBeInTheDocument();
    // The first page stays: the pager appends, it doesn't replace.
    expect(screen.getByRole('link', { name: 'Cordless drill' })).toBeInTheDocument();
    // DRF hands back an absolute URL; sending it verbatim would be cross-origin
    // and would drop the auth cookies.
    const [secondUrl] = apiFetch.mock.calls[1];
    expect(secondUrl).toBe('/api/v1/owner-bookings/?page=2');
    // Exhausted, the pager stands down rather than fetching the same page again.
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Load more' })).toBeNull());
  });

  test('no "Load more" when the first page is the only page', async () => {
    mockApi([{ results: [booking()], next: null }]);
    renderPage();
    await screen.findByRole('link', { name: 'Cordless drill' });

    expect(screen.queryByRole('button', { name: 'Load more' })).toBeNull();
  });
});

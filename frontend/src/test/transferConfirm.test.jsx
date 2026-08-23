import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router';
import { vi, describe, test, expect, beforeEach, afterEach } from 'vitest';

vi.mock('../services/api', () => ({
  apiFetch: vi.fn(),
  getCsrfToken: () => 'tok',
  extractApiError: () => null,
}));

import { apiFetch } from '../services/api';
import OwnerBookingsPage from '../pages/OwnerBookingsPage';
import ThingPage from '../pages/ThingPage';

// Accepting a GIFT or SELL that isn't endless hands the thing over for good:
// `accept_booking` flips it INACTIVE, adds the requester to `deal` and writes a
// ThingTransfer. There is no undo.
//
// The warning for it existed in ThingPage, translated into three languages, and
// had NEVER rendered: the page destructured `acceptTransfersOwnership` from
// `useThingActions`, which never returned it, so the flag read `undefined` and
// the ternary always fell to the plain button. These tests exist because that
// failure was completely silent — nothing broke, the guard was simply absent.
function booking(over = {}) {
  return {
    code: 'BKG001',
    created: '2026-08-01T10:00:00Z',
    thing_code: 'THG001',
    thing_headline: 'Blue armchair',
    thing_type: 'GIFT_THING',
    thing_is_endless: false,
    requester_code: 'USR002',
    requester_name: 'Lele',
    owner_code: 'USR001',
    start_date: null,
    end_date: null,
    status: 'PENDING',
    ...over,
  };
}

function renderPage(rows) {
  apiFetch.mockImplementation((url, opts) => {
    if (opts?.method === 'POST')
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
    return Promise.resolve({
      ok: true,
      json: () => Promise.resolve({ results: rows, next: null }),
    });
  });
  return render(
    <MemoryRouter initialEntries={['/owner-bookings']}>
      <Routes>
        <Route path="/owner-bookings" element={<OwnerBookingsPage />} />
      </Routes>
    </MemoryRouter>
  );
}

const acceptButton = () => screen.getByRole('button', { name: /Confirm this request/i });
const postCalls = () => apiFetch.mock.calls.filter(([, o]) => o?.method === 'POST').map(([u]) => u);

describe('Accepting a request that hands the thing over', () => {
  beforeEach(() => {
    localStorage.clear();
    localStorage.setItem('userCode', 'USR001');
    vi.clearAllMocks();
  });
  afterEach(() => vi.restoreAllMocks());

  test('a gift asks before it changes hands, and only accepts once confirmed', async () => {
    renderPage([booking()]);
    await screen.findByText('Blue armchair');

    fireEvent.click(acceptButton());

    // By role, not by text: the phrase appears in both the heading and the
    // confirm button, so a text matcher finds two nodes and throws.
    expect(await screen.findByRole('dialog')).toBeInTheDocument();
    expect(postCalls()).toEqual([]); // nothing committed on the first click

    fireEvent.click(screen.getByRole('button', { name: 'Transfer ownership' }));

    await waitFor(() => expect(postCalls()).toEqual(['/api/v1/bookings/BKG001/accept/']));
  });

  test('cancelling the confirm leaves the request untouched', async () => {
    renderPage([booking()]);
    await screen.findByText('Blue armchair');

    fireEvent.click(acceptButton());
    await screen.findByRole('dialog');
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(postCalls()).toEqual([]);
  });

  test('a loan accepts straight away — it comes back, nothing is transferred', async () => {
    renderPage([
      booking({ thing_type: 'LEND_THING', start_date: '2099-01-01', end_date: '2099-01-08' }),
    ]);
    await screen.findByText('Blue armchair');

    fireEvent.click(acceptButton());

    await waitFor(() => expect(postCalls()).toEqual(['/api/v1/bookings/BKG001/accept/']));
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  test('an endless gift accepts straight away — it is given again and again', async () => {
    // The reason `thing_type` alone can't answer the question: this is a GIFT,
    // but an endless one keeps its status and writes no transfer, so warning
    // about a handover here would describe something that will not happen.
    renderPage([booking({ thing_is_endless: true })]);
    await screen.findByText('Blue armchair');

    fireEvent.click(acceptButton());

    await waitFor(() => expect(postCalls()).toEqual(['/api/v1/bookings/BKG001/accept/']));
    expect(screen.queryByRole('dialog')).toBeNull();
  });
});

// The same guard on the thing's own page, which is where the confirm was
// written and where it had been dead. `useThingActions` returning the flag is
// what revives it, so this asserts the rendered outcome rather than the flag.
describe('ThingPage — the confirm that was never shown', () => {
  beforeEach(() => {
    localStorage.clear();
    localStorage.setItem('userCode', 'USR001');
    vi.clearAllMocks();
  });
  afterEach(() => vi.restoreAllMocks());

  function renderThing(thing) {
    apiFetch.mockImplementation((url, opts) => {
      if (opts?.method === 'POST')
        return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
      if (url.includes('/faq/'))
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ results: [] }) });
      if (url.includes('/transfers/'))
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ total_transfers: 0, transfers: [] }),
        });
      return Promise.resolve({ ok: true, json: () => Promise.resolve(thing) });
    });
    return render(
      <MemoryRouter initialEntries={['/things/THG001']}>
        <Routes>
          <Route path="/things/:thingCode" element={<ThingPage />} />
        </Routes>
      </MemoryRouter>
    );
  }

  const takenGift = {
    code: 'THG001',
    type: 'GIFT_THING',
    headline: 'Blue armchair',
    description: '',
    status: 'TAKEN',
    owner: 'USR001',
    owner_name: 'Me',
    is_endless: false,
    thumbnail_url: '',
    gallery_urls: [],
    tags: [],
    collection_tags: [],
    pending_questions: 0,
    pending_booking: 'BKG001',
    my_pending_booking: null,
    bookings: [
      {
        code: 'BKG001',
        requester_name: 'Lele',
        start_date: null,
        end_date: null,
        status: 'PENDING',
        created: '2026-08-01T10:00:00Z',
      },
    ],
  };

  test('accepting a taken gift asks first, and commits only on confirm', async () => {
    renderThing(takenGift);
    await screen.findByText('Blue armchair');

    fireEvent.click(await screen.findByRole('button', { name: /Confirm hold/i }));

    expect(await screen.findByText(/transfers the item/i)).toBeInTheDocument();
    expect(postCalls()).toEqual([]);

    fireEvent.click(screen.getByRole('button', { name: 'Transfer ownership' }));
    await waitFor(() => expect(postCalls()).toEqual(['/api/v1/bookings/BKG001/accept/']));
  });

  test('an endless gift is accepted without the transfer warning', async () => {
    renderThing({ ...takenGift, status: 'TAKEN', is_endless: true });
    await screen.findByText('Blue armchair');

    fireEvent.click(await screen.findByRole('button', { name: /Confirm hold/i }));

    await waitFor(() => expect(postCalls()).toEqual(['/api/v1/bookings/BKG001/accept/']));
    expect(screen.queryByText(/transfers the item/i)).toBeNull();
  });
});

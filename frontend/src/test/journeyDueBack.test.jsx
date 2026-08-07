import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router';
import { vi, describe, test, expect, beforeEach } from 'vitest';

window.scrollTo = vi.fn();

vi.mock('../services/api', () => ({
  apiFetch: vi.fn(),
  getCsrfToken: vi.fn(() => 'mock-csrf'),
}));

import { apiFetch } from '../services/api';
import ThingPage from '../pages/ThingPage';

const ok = (body) => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });

const THING = {
  code: 'THG001',
  headline: 'A cordless drill',
  description: '',
  type: 'LEND_THING',
  status: 'ACTIVE',
  owner: 'OWN001',
  owner_name: 'Lili',
  created: '2026-07-01T10:00:00Z',
  thumbnail_url: '',
  gallery_urls: [],
  tags: [],
  collection_code: 'COL001',
};

const journey = (autoClosed) => ({
  total_transfers: 1,
  unique_homes: 2,
  current_holder: null,
  current_holder_name: null,
  original_owner: 'OWN001',
  original_owner_name: 'Lili',
  transfers: [{
    code: 'TRF001',
    from_user: 'OWN001',
    to_user: 'BOR001',
    from_user_name: 'Lili',
    to_user_name: 'Lele',
    lent_date: '2026-07-20',
    returned_date: '2026-07-27',
    auto_closed: autoClosed,
  }],
});

const setApi = (autoClosed) => {
  apiFetch.mockImplementation((url) => {
    if (url.includes('/transfers/')) return ok(journey(autoClosed));
    if (url.includes('/faq/')) return ok({ results: [] });
    if (url.includes('/calendar/')) return ok([]);
    if (url.includes('/things/')) return ok(THING);
    return ok({});
  });
};

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem('userCode', 'SOMEBODY');
  vi.clearAllMocks();
});

const renderThing = () =>
  render(
    <MemoryRouter initialEntries={['/things/THG001']}>
      <Routes>
        <Route path="/things/:thingCode" element={<ThingPage />} />
      </Routes>
    </MemoryRouter>
  );

/**
 * The journey must not narrate a handover nobody witnessed.
 *
 * `close_transfers` stamps a return date once the booking's end_date passes —
 * whether or not the thing came back. Printing that as "Returned on {date}"
 * made the product's most human surface ("this item has travelled to 4 homes")
 * tell a story it has no evidence for.
 */
describe('Journey timeline', () => {
  test('an inferred close reads as a due date, not a return', async () => {
    setApi(true);
    renderThing();

    expect(await screen.findByText(/Due back on/)).toBeInTheDocument();
    expect(screen.queryByText(/Returned on/)).not.toBeInTheDocument();
  });

  test('a genuine handover still reads as a return', async () => {
    setApi(false);
    renderThing();

    expect(await screen.findByText(/Returned on/)).toBeInTheDocument();
    expect(screen.queryByText(/Due back on/)).not.toBeInTheDocument();
  });
});

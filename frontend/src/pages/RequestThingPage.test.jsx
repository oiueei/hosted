import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router';
import { describe, test, expect, vi, afterEach, beforeEach } from 'vitest';
import RequestThingPage from './RequestThingPage';

// utils/rental.js is unit-tested on its own — these tests protect the PAGE's
// wiring: what the pickers produce must be what the POST body carries.

// Dynamic dates keep the test valid on any run day: the next Monday at least
// two days out is always inside the [today, today+90] picker range.
function nextMonday() {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  d.setDate(d.getDate() + 2);
  while (d.getDay() !== 1) d.setDate(d.getDate() + 1);
  return d;
}
// Local-date ISO — toISOString() is UTC and would slide midnight back a day.
const iso = (d) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
const display = (d) =>
  `${String(d.getDate()).padStart(2, '0')}/${String(d.getMonth() + 1).padStart(2, '0')}/${d.getFullYear()}`;
const plusDays = (d, n) => {
  const c = new Date(d);
  c.setDate(c.getDate() + n);
  return c;
};

// The same JSON shapes the DRF serializers emit (subset the page reads).
const RENTAL_THING = {
  code: 'RTHG01',
  headline: 'Drill',
  type: 'RENT_THING',
  fee: '5.00',
  rental_durations: [7],
  rental_weekdays: [0, 1, 2, 3, 4],
  available_today: true,
  next_available: iso(new Date()),
  collection_code: 'RCOL01',
};

function mockRoutes({ thing, ownThings = [], request = { ok: true, status: 201 } }) {
  globalThis.fetch = vi.fn((url, options = {}) => {
    const respond = (status, body) =>
      Promise.resolve({ ok: status < 400, status, json: async () => body });
    if (url.endsWith('/calendar/')) return respond(200, []);
    if (url.endsWith('/request/')) return respond(request.status, request.body ?? { message: 'Booking request sent', booking_code: 'BK0001' });
    if (url === '/api/v1/things/') return respond(200, { results: ownThings });
    if (options.method === undefined || options.method === 'GET') return respond(200, thing);
    return respond(404, {});
  });
}

function renderPage(collectionCode, thingCode) {
  return render(
    <MemoryRouter initialEntries={[`/collections/${collectionCode}/things/${thingCode}/request`]}>
      <Routes>
        <Route path="/collections/:code/things/:thingCode/request" element={<RequestThingPage />} />
      </Routes>
    </MemoryRouter>
  );
}

describe('RequestThingPage (what the pickers produce is what the POST carries)', () => {
  beforeEach(() => {
    localStorage.setItem('userCode', 'TEST01');
  });
  afterEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
  });

  test('a rules-bound rental derives the return date and POSTs it with the collection code', async () => {
    mockRoutes({ thing: RENTAL_THING });
    renderPage('RCOL01', 'RTHG01');
    await screen.findByText('Rental length');

    const pickup = nextMonday();
    // The single fixed length is preselected (#4), so the pickup picker is live.
    // HDS DateInput commits its value on blur, not per keystroke.
    const input = screen.getByLabelText(/Pickup date/);
    fireEvent.change(input, { target: { value: display(pickup) } });
    fireEvent.blur(input);

    // A one-week rental picked up on a Monday returns the NEXT Monday.
    const returnDay = plusDays(pickup, 7);
    expect(screen.getByText(`Return by ${display(returnDay)}`)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Rent' }));

    await screen.findByText("You're all set!");
    const [url, options] = globalThis.fetch.mock.calls.find(([u]) => u.endsWith('/request/'));
    expect(url).toBe('/api/v1/things/RTHG01/request/');
    expect(JSON.parse(options.body)).toEqual({
      start_date: iso(pickup),
      end_date: iso(returnDay),
      collection_code: 'RCOL01',
    });
  });

  test('a 409 overlap shows the date-overlap message and no success screen', async () => {
    mockRoutes({ thing: RENTAL_THING, request: { status: 409, body: { error: 'overlap' } } });
    renderPage('RCOL01', 'RTHG01');
    await screen.findByText('Rental length');

    const input = screen.getByLabelText(/Pickup date/);
    fireEvent.change(input, { target: { value: display(nextMonday()) } });
    fireEvent.blur(input);
    fireEvent.click(screen.getByRole('button', { name: 'Rent' }));

    expect(await screen.findByText('Date overlaps with another booking.')).toBeInTheDocument();
    expect(screen.queryByText("You're all set!")).not.toBeInTheDocument();
  });


});

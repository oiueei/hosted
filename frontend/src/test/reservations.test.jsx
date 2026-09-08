import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router';
import { vi, describe, test, expect, beforeEach, afterEach } from 'vitest';

window.scrollTo = vi.fn();

vi.mock('../services/api', () => ({
  apiFetch: vi.fn(() =>
    Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) })
  ),
  extractApiError: vi.fn(() => Promise.resolve('')),
  getCsrfToken: vi.fn(() => 'mock-csrf'),
}));

import { apiFetch } from '../services/api';
import RequestThingPage from '../pages/RequestThingPage';
import InboxNotifications from '../components/InboxNotifications';

function mockResponse(data, ok = true) {
  return { ok, status: ok ? 200 : 400, json: () => Promise.resolve(data) };
}

const RESERVE_THING = {
  code: 'RSV01',
  type: 'RESERVE_THING',
  headline: 'Sala polivalent',
  fee: '5.00',
  location: 'Planta 1',
  collection_code: 'COL001',
  rental_weekdays: [],
  reservation_max_days: 3,
  available_today: true,
  next_available: null,
};

function setApi({ thing = RESERVE_THING, calendar = [], postOk = true } = {}) {
  apiFetch.mockImplementation((url, opts = {}) => {
    if (/\/things\/[^/]+\/calendar\//.test(url)) return Promise.resolve(mockResponse(calendar));
    if (/\/things\/[^/]+\/request\//.test(url) && opts.method === 'POST') {
      return Promise.resolve(
        mockResponse({ message: 'Reservation confirmed', booking_code: 'B1' }, postOk)
      );
    }
    if (/\/things\/[^/]+\/$/.test(url)) return Promise.resolve(mockResponse(thing));
    return Promise.resolve(mockResponse({}));
  });
}

function renderPage() {
  return render(
    <MemoryRouter
      initialEntries={[{ pathname: '/collections/COL001/things/RSV01/request', state: {} }]}
    >
      <Routes>
        <Route path="/collections/:code/things/:thingCode/request" element={<RequestThingPage />} />
        <Route path="*" element={<div data-testid="navigated" />} />
      </Routes>
    </MemoryRouter>
  );
}

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem('userCode', 'ABC123');
  localStorage.setItem('koro', 'basic');
  vi.clearAllMocks();
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(new Date(2026, 5, 1, 12, 0, 0)); // Mon 2026-06-01
  setApi();
});

afterEach(() => {
  vi.useRealTimers();
});

function typePickup(container, display) {
  const input = container.querySelector('#reservation-pickup-date');
  fireEvent.change(input, { target: { value: display } });
  fireEvent.blur(input);
}

describe('RequestThingPage — RESERVE_THING', () => {
  test('with max 1 day there is no duration select, and a project note field is shown', async () => {
    setApi({ thing: { ...RESERVE_THING, reservation_max_days: 1 } });
    renderPage();
    await screen.findByText(/Reserve Sala polivalent/);
    expect(screen.queryByRole('combobox', { name: /How many days/ })).toBeNull();
    expect(screen.getByLabelText(/Tell us briefly about your project/)).toBeInTheDocument();
  });

  test('with a longer cap the duration select is offered', async () => {
    renderPage();
    await screen.findByText(/Reserve Sala polivalent/);
    expect(screen.getByRole('combobox', { name: /How many days/ })).toBeInTheDocument();
  });

  test('the date picker stops at the collection horizon, not the fixed 90', async () => {
    // horizon 7 days from Mon 2026-06-01 → last bookable day is 2026-06-08
    setApi({ thing: { ...RESERVE_THING, reservation_max_days: 1, reservation_horizon_days: 7 } });
    renderPage();
    await screen.findByText(/Reserve Sala polivalent/);
    fireEvent.click(screen.getByRole('button', { name: 'Choose date' }));
    await waitFor(() => expect(document.querySelector('[data-date]')).toBeTruthy());
    // 2026-06-05 is within the 7-day window — selectable
    expect(document.querySelector('[data-date="2026-06-05"]')?.tagName).toBe('BUTTON');
    // 2026-06-09 is past it — rendered disabled (span, not button) or absent
    const past = document.querySelector('[data-date="2026-06-09"]');
    expect(past === null || past.getAttribute('aria-disabled') === 'true').toBe(true);
  });

  test('submitting posts a duration + note and shows the confirmed message', async () => {
    setApi({ thing: { ...RESERVE_THING, reservation_max_days: 1 } });
    const { container } = renderPage();
    await screen.findByText(/Reserve Sala polivalent/);

    fireEvent.change(screen.getByLabelText(/Tell us briefly about your project/), {
      target: { value: 'A screen-printing workshop.' },
    });
    typePickup(container, '03/06/2026');
    fireEvent.click(screen.getByRole('button', { name: 'Reserve' }));

    await screen.findByText(/Your reservation is confirmed/);
    const postCall = apiFetch.mock.calls.find(
      ([url, opts]) => /\/request\//.test(url) && opts?.method === 'POST'
    );
    const body = JSON.parse(postCall[1].body);
    expect(body).toMatchObject({
      start_date: '2026-06-03',
      duration_days: 1,
      project_note: 'A screen-printing workshop.',
      collection_code: 'COL001',
    });
  });
});

describe('InboxNotifications — reservation notices render (not the blank broadcast fallback)', () => {
  function setInbox(rows) {
    apiFetch.mockImplementation((url) => {
      if (url.startsWith('/api/v1/inbox')) return Promise.resolve(mockResponse(rows));
      return Promise.resolve(mockResponse({}));
    });
  }

  test('RESERVATION_MADE', async () => {
    setInbox([
      {
        code: 'N1',
        type: 'RESERVATION_MADE',
        payload: { requester_name: 'Lele', thing_headline: 'Sala 2', thing_code: 'T1' },
        created: '2026-06-01T10:00:00Z',
      },
    ]);
    render(
      <MemoryRouter>
        <InboxNotifications />
      </MemoryRouter>
    );
    expect(await screen.findByText('New reservation')).toBeInTheDocument();
    expect(screen.getByText('Lele reserved Sala 2.')).toBeInTheDocument();
  });

  test('RESERVATION_CANCELLED', async () => {
    setInbox([
      {
        code: 'N2',
        type: 'RESERVATION_CANCELLED',
        payload: { other_name: 'Lala', thing_headline: 'Sala 2', thing_code: 'T1' },
        created: '2026-06-01T10:00:00Z',
      },
    ]);
    render(
      <MemoryRouter>
        <InboxNotifications />
      </MemoryRouter>
    );
    expect(await screen.findByText('Reservation cancelled')).toBeInTheDocument();
    expect(screen.getByText('Lala cancelled a reservation of Sala 2.')).toBeInTheDocument();
  });
});

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
    // horizon 7 days from Mon 2026-06-01 → pickup on 2026-06-08 is the last day,
    // and the backend's reservation_violation now agrees (it judges the pickup
    // day, not the exclusive end_date — Collection.reservation_violation).
    setApi({ thing: { ...RESERVE_THING, reservation_max_days: 1, reservation_horizon_days: 7 } });
    renderPage();
    await screen.findByText(/Reserve Sala polivalent/);
    fireEvent.click(screen.getByRole('button', { name: 'Choose date' }));
    await waitFor(() => expect(document.querySelector('[data-date]')).toBeTruthy());
    // 2026-06-05 is within the 7-day window — selectable
    expect(document.querySelector('[data-date="2026-06-05"]')?.tagName).toBe('BUTTON');
    // 2026-06-08 is exactly the horizon — still selectable (the off-by-one the
    // server used to reject on this very day).
    expect(document.querySelector('[data-date="2026-06-08"]')?.tagName).toBe('BUTTON');
    // 2026-06-09 is past it — rendered disabled (span, not button) or absent
    const past = document.querySelector('[data-date="2026-06-09"]');
    expect(past === null || past.getAttribute('aria-disabled') === 'true').toBe(true);
  });

  test('the pickup field explains why some days are greyed out', async () => {
    setApi({ thing: { ...RESERVE_THING, reservation_max_days: 1 } });
    renderPage();
    await screen.findByText(/Reserve Sala polivalent/);
    expect(screen.getByText(/greyed out/i)).toBeInTheDocument();
  });

  test('a multi-day reservation shows the span it will book before you confirm', async () => {
    // Default RESERVE_THING: max 3 days, weekdays unrestricted. System time is
    // Mon 2026-06-01, so 03/06 is a Wednesday and free.
    const { container } = renderPage();
    await screen.findByText(/Reserve Sala polivalent/);

    fireEvent.click(screen.getByRole('combobox', { name: /How many days/ }));
    fireEvent.click(await screen.findByRole('option', { name: '3 days' }));
    typePickup(container, '03/06/2026');

    // Three days from the 3rd covers the 3rd, 4th and 5th — the last day is
    // inclusive, and the reservation auto-confirms with no owner step to catch
    // a wrong end.
    expect(await screen.findByText('Reserved from 03/06/2026 to 05/06/2026.')).toBeInTheDocument();
  });

  test('a date past the collection horizon is rejected with the collection’s own limit', async () => {
    setApi({ thing: { ...RESERVE_THING, reservation_max_days: 1, reservation_horizon_days: 7 } });
    const { container } = renderPage();
    await screen.findByText(/Reserve Sala polivalent/);

    typePickup(container, '30/06/2026'); // well past today + 7 days
    expect(await screen.findByText(/between today and 7 days from now/i)).toBeInTheDocument();
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

  test('a 403 (not a member) auto-joins the PUBLIC collection and completes the reservation, with no extra click', async () => {
    setApi({ thing: { ...RESERVE_THING, reservation_max_days: 1 } });
    let joinCalled = false;
    let requestCalls = 0;
    apiFetch.mockImplementation((url, opts = {}) => {
      if (/\/collections\/COL001\/join\//.test(url) && opts.method === 'POST') {
        joinCalled = true;
        return Promise.resolve(mockResponse({ message: 'Joined' }));
      }
      if (/\/things\/[^/]+\/request\//.test(url) && opts.method === 'POST') {
        requestCalls += 1;
        if (requestCalls === 1) {
          return Promise.resolve({
            ok: false,
            status: 403,
            json: () =>
              Promise.resolve({
                error: 'You need to be a member of this group to reserve.',
                code: 'not_a_member',
              }),
          });
        }
        return Promise.resolve(
          mockResponse({ message: 'Reservation confirmed', booking_code: 'B1' })
        );
      }
      if (/\/things\/[^/]+\/calendar\//.test(url)) return Promise.resolve(mockResponse([]));
      if (/\/things\/[^/]+\/$/.test(url))
        return Promise.resolve(mockResponse({ ...RESERVE_THING, reservation_max_days: 1 }));
      return Promise.resolve(mockResponse({}));
    });
    const { container } = renderPage();
    await screen.findByText(/Reserve Sala polivalent/);

    typePickup(container, '03/06/2026');
    fireEvent.click(screen.getByRole('button', { name: 'Reserve' }));

    // one click, and it just works — no "not a member" text, no join button
    // ever shown, straight to the confirmation.
    expect(await screen.findByText(/Your reservation is confirmed/)).toBeInTheDocument();
    expect(joinCalled).toBe(true);
    expect(requestCalls).toBe(2); // the failed attempt, then the auto-retry
    expect(
      screen.queryByText('You need to be a member of this group to reserve.')
    ).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Join this group' })).not.toBeInTheDocument();
  });

  test('a failed auto-join falls back to the reason plus a manual retry button', async () => {
    setApi({ thing: { ...RESERVE_THING, reservation_max_days: 1 } });
    apiFetch.mockImplementation((url, opts = {}) => {
      if (/\/collections\/COL001\/join\//.test(url) && opts.method === 'POST') {
        return Promise.resolve({ ok: false, status: 500, json: () => Promise.resolve({}) });
      }
      if (/\/things\/[^/]+\/request\//.test(url) && opts.method === 'POST') {
        return Promise.resolve({
          ok: false,
          status: 403,
          json: () =>
            Promise.resolve({
              error: 'You need to be a member of this group to reserve.',
              code: 'not_a_member',
            }),
        });
      }
      if (/\/things\/[^/]+\/calendar\//.test(url)) return Promise.resolve(mockResponse([]));
      if (/\/things\/[^/]+\/$/.test(url))
        return Promise.resolve(mockResponse({ ...RESERVE_THING, reservation_max_days: 1 }));
      return Promise.resolve(mockResponse({}));
    });
    const { container } = renderPage();
    await screen.findByText(/Reserve Sala polivalent/);

    typePickup(container, '03/06/2026');
    fireEvent.click(screen.getByRole('button', { name: 'Reserve' }));

    // the auto-join attempt failed silently in the background, so the reader
    // sees the original reason plus a way to try again themselves
    expect(
      await screen.findByText('You need to be a member of this group to reserve.')
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Join this group' })).toBeInTheDocument();
    expect(screen.queryByText(/Your reservation is confirmed/)).not.toBeInTheDocument();
  });

  test('the manual fallback button retries the join and the exact same reservation', async () => {
    setApi({ thing: { ...RESERVE_THING, reservation_max_days: 1 } });
    let joinCalls = 0;
    let requestCalls = 0;
    apiFetch.mockImplementation((url, opts = {}) => {
      if (/\/collections\/COL001\/join\//.test(url) && opts.method === 'POST') {
        joinCalls += 1;
        // fails the first (automatic) attempt, succeeds the second (manual)
        if (joinCalls === 1) {
          return Promise.resolve({ ok: false, status: 500, json: () => Promise.resolve({}) });
        }
        return Promise.resolve(mockResponse({ message: 'Joined' }));
      }
      if (/\/things\/[^/]+\/request\//.test(url) && opts.method === 'POST') {
        requestCalls += 1;
        if (requestCalls === 1) {
          return Promise.resolve({
            ok: false,
            status: 403,
            json: () =>
              Promise.resolve({
                error: 'You need to be a member of this group to reserve.',
                code: 'not_a_member',
              }),
          });
        }
        return Promise.resolve(
          mockResponse({ message: 'Reservation confirmed', booking_code: 'B1' })
        );
      }
      if (/\/things\/[^/]+\/calendar\//.test(url)) return Promise.resolve(mockResponse([]));
      if (/\/things\/[^/]+\/$/.test(url))
        return Promise.resolve(mockResponse({ ...RESERVE_THING, reservation_max_days: 1 }));
      return Promise.resolve(mockResponse({}));
    });
    const { container } = renderPage();
    await screen.findByText(/Reserve Sala polivalent/);

    typePickup(container, '03/06/2026');
    fireEvent.click(screen.getByRole('button', { name: 'Reserve' }));
    await screen.findByRole('button', { name: 'Join this group' });

    fireEvent.click(screen.getByRole('button', { name: 'Join this group' }));

    expect(await screen.findByText(/Your reservation is confirmed/)).toBeInTheDocument();
    expect(joinCalls).toBe(2);
    expect(requestCalls).toBe(2); // never re-typed — the form still says 03/06
  });

  test('a 403 without the not_a_member marker never auto-joins — it just shows the reason', async () => {
    // The thing going INACTIVE while this form was open, say: still a 403,
    // still carries an `error`, but not the one auto-join is for.
    setApi({ thing: { ...RESERVE_THING, reservation_max_days: 1 } });
    let joinCalled = false;
    apiFetch.mockImplementation((url, opts = {}) => {
      if (/\/collections\/COL001\/join\//.test(url) && opts.method === 'POST') {
        joinCalled = true;
        return Promise.resolve(mockResponse({ message: 'Joined' }));
      }
      if (/\/things\/[^/]+\/request\//.test(url) && opts.method === 'POST') {
        return Promise.resolve({
          ok: false,
          status: 403,
          json: () => Promise.resolve({ error: 'Not authorized to request this thing' }),
        });
      }
      if (/\/things\/[^/]+\/calendar\//.test(url)) return Promise.resolve(mockResponse([]));
      if (/\/things\/[^/]+\/$/.test(url))
        return Promise.resolve(mockResponse({ ...RESERVE_THING, reservation_max_days: 1 }));
      return Promise.resolve(mockResponse({}));
    });
    const { container } = renderPage();
    await screen.findByText(/Reserve Sala polivalent/);

    typePickup(container, '03/06/2026');
    fireEvent.click(screen.getByRole('button', { name: 'Reserve' }));

    expect(await screen.findByText('Not authorized to request this thing')).toBeInTheDocument();
    expect(joinCalled).toBe(false);
    expect(screen.queryByRole('button', { name: 'Join this group' })).not.toBeInTheDocument();
  });

  test('the manual fallback books the date on screen now, not the one from the failed attempt', async () => {
    setApi({ thing: { ...RESERVE_THING, reservation_max_days: 1 } });
    let joinCalls = 0;
    const requestDates = [];
    apiFetch.mockImplementation((url, opts = {}) => {
      if (/\/collections\/COL001\/join\//.test(url) && opts.method === 'POST') {
        joinCalls += 1;
        if (joinCalls === 1) {
          return Promise.resolve({ ok: false, status: 500, json: () => Promise.resolve({}) });
        }
        return Promise.resolve(mockResponse({ message: 'Joined' }));
      }
      if (/\/things\/[^/]+\/request\//.test(url) && opts.method === 'POST') {
        const parsed = JSON.parse(opts.body);
        requestDates.push(parsed.start_date);
        if (requestDates.length === 1) {
          return Promise.resolve({
            ok: false,
            status: 403,
            json: () =>
              Promise.resolve({
                error: 'You need to be a member of this group to reserve.',
                code: 'not_a_member',
              }),
          });
        }
        return Promise.resolve(
          mockResponse({ message: 'Reservation confirmed', booking_code: 'B1' })
        );
      }
      if (/\/things\/[^/]+\/calendar\//.test(url)) return Promise.resolve(mockResponse([]));
      if (/\/things\/[^/]+\/$/.test(url))
        return Promise.resolve(mockResponse({ ...RESERVE_THING, reservation_max_days: 1 }));
      return Promise.resolve(mockResponse({}));
    });
    const { container } = renderPage();
    await screen.findByText(/Reserve Sala polivalent/);

    typePickup(container, '03/06/2026');
    fireEvent.click(screen.getByRole('button', { name: 'Reserve' }));
    await screen.findByRole('button', { name: 'Join this group' });

    // the reader changes their mind about the date while the fallback is showing
    typePickup(container, '05/06/2026');
    fireEvent.click(screen.getByRole('button', { name: 'Join this group' }));

    expect(await screen.findByText(/Your reservation is confirmed/)).toBeInTheDocument();
    expect(requestDates).toEqual(['2026-06-03', '2026-06-05']);
  });
});

describe("RequestThingPage — the collection's request-page note", () => {
  test('renders as Markdown under the title when the collection set one', async () => {
    setApi({
      thing: {
        ...RESERVE_THING,
        reservation_max_days: 1,
        collection_request_info: 'Bring **photo ID** to the front desk.',
      },
    });
    renderPage();
    await screen.findByText(/Reserve Sala polivalent/);

    const strong = screen.getByText('photo ID');
    expect(strong.tagName).toBe('STRONG');
    expect(strong.closest('.form-hero-text')).toBeInTheDocument();
  });

  test('is absent when the collection has no note', async () => {
    setApi({ thing: { ...RESERVE_THING, reservation_max_days: 1 } });
    renderPage();
    await screen.findByText(/Reserve Sala polivalent/);

    expect(document.querySelector('.form-hero-text')).toBeNull();
  });
});

const HOURLY_RESERVE_THING = {
  code: 'RSV01',
  type: 'RESERVE_THING',
  headline: 'Sala amb hores',
  location: 'Planta 1',
  collection_code: 'COL001',
  reservation_unit: 'HOUR',
  reservation_horizon_days: 90,
  reservation_max_hours: 3,
  // CA's own schedule: Mon-Thu 10-14 & 16-20, Fri 10-14, weekend closed.
  opening_hours: {
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
  },
  available_today: true,
  next_available: null,
};

function typeHourlyPickup(container, display) {
  const input = container.querySelector('#reservation-pickup-date-hourly');
  fireEvent.change(input, { target: { value: display } });
  fireEvent.blur(input);
}

describe('RequestThingPage — RESERVE_THING (HOUR unit)', () => {
  test('renders the hourly pickup field, not the day-count select', async () => {
    setApi({ thing: HOURLY_RESERVE_THING });
    renderPage();
    await screen.findByText(/Reserve Sala amb hores/);
    expect(screen.queryByRole('combobox', { name: /How many days/ })).toBeNull();
    expect(document.querySelector('#reservation-pickup-date-hourly')).toBeInTheDocument();
  });

  test('picking a day reveals the duration radios, capped at reservation_max_hours', async () => {
    setApi({ thing: HOURLY_RESERVE_THING });
    const { container } = renderPage();
    await screen.findByText(/Reserve Sala amb hores/);

    typeHourlyPickup(container, '03/06/2026'); // a Wednesday, both blocks open

    expect(await screen.findByRole('radio', { name: '1 hour' })).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: '2 hours' })).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: '3 hours' })).toBeInTheDocument();
    // 4h (half day) and 10h (full day) both exceed the 3h cap — not offered.
    expect(screen.queryByRole('radio', { name: 'Half day' })).toBeNull();
    expect(screen.queryByRole('radio', { name: 'Full day' })).toBeNull();
  });

  test('a single-block day (Friday) offers "Full day" once it fits the cap', async () => {
    setApi({ thing: { ...HOURLY_RESERVE_THING, reservation_max_hours: 4 } });
    const { container } = renderPage();
    await screen.findByText(/Reserve Sala amb hores/);

    typeHourlyPickup(container, '05/06/2026'); // Friday, single 10:00-14:00 block

    expect(await screen.findByRole('radio', { name: 'Full day' })).toBeInTheDocument();
    expect(screen.queryByRole('radio', { name: 'Half day' })).toBeNull(); // one block only
  });

  test('picking a duration reveals the start-time radios, stepped hour by hour', async () => {
    setApi({ thing: HOURLY_RESERVE_THING });
    const { container } = renderPage();
    await screen.findByText(/Reserve Sala amb hores/);

    typeHourlyPickup(container, '03/06/2026');
    fireEvent.click(await screen.findByRole('radio', { name: '2 hours' }));

    // 10:00-14:00 fits 10:00,11:00,12:00 for a 2h slot; 16:00-20:00 fits
    // 16:00,17:00,18:00.
    for (const hm of ['10:00', '11:00', '12:00', '16:00', '17:00', '18:00']) {
      expect(await screen.findByRole('radio', { name: hm })).toBeInTheDocument();
    }
    expect(screen.queryByRole('radio', { name: '13:00' })).toBeNull(); // would end at 15:00
  });

  test('a fully booked day is disabled in the picker itself', async () => {
    setApi({
      thing: HOURLY_RESERVE_THING,
      calendar: [
        {
          start_date: '2026-06-03',
          end_date: '2026-06-04',
          start_time: '10:00',
          end_time: '14:00',
        },
        {
          start_date: '2026-06-03',
          end_date: '2026-06-04',
          start_time: '16:00',
          end_time: '20:00',
        },
      ],
    });
    renderPage();
    await screen.findByText(/Reserve Sala amb hores/);

    fireEvent.click(screen.getByRole('button', { name: 'Choose date' }));
    await waitFor(() => expect(document.querySelector('[data-date]')).toBeTruthy());
    const day3 = document.querySelector('[data-date="2026-06-03"]');
    expect(day3 === null || day3.getAttribute('aria-disabled') === 'true').toBe(true);
  });

  test('choosing a duration that fits nowhere that day shows the fallback notice', async () => {
    // Two separate 1h gaps remain (13:00-14:00 and 19:00-20:00): the day still
    // has a free hour, so the picker allows it, but no 2h+ slot fits either
    // gap — "2 hours" should fall back to the notice, not an empty radio group.
    setApi({
      thing: HOURLY_RESERVE_THING,
      calendar: [
        {
          start_date: '2026-06-03',
          end_date: '2026-06-04',
          start_time: '10:00',
          end_time: '13:00',
        },
        {
          start_date: '2026-06-03',
          end_date: '2026-06-04',
          start_time: '16:00',
          end_time: '19:00',
        },
      ],
    });
    const { container } = renderPage();
    await screen.findByText(/Reserve Sala amb hores/);

    typeHourlyPickup(container, '03/06/2026');
    fireEvent.click(await screen.findByRole('radio', { name: '1 hour' }));
    expect(await screen.findByRole('radio', { name: '13:00' })).toBeInTheDocument();
    expect(await screen.findByRole('radio', { name: '19:00' })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('radio', { name: '2 hours' }));
    expect(await screen.findByText(/No start times are free/)).toBeInTheDocument();
    expect(screen.queryByRole('radio', { name: '13:00' })).toBeNull();
  });

  test('submitting posts start_time/end_time (never duration_days) for an hourly reservation', async () => {
    setApi({ thing: HOURLY_RESERVE_THING });
    const { container } = renderPage();
    await screen.findByText(/Reserve Sala amb hores/);

    typeHourlyPickup(container, '03/06/2026');
    fireEvent.click(await screen.findByRole('radio', { name: '2 hours' }));
    fireEvent.click(await screen.findByRole('radio', { name: '11:00' }));
    fireEvent.change(screen.getByLabelText(/Tell us briefly about your project/), {
      target: { value: 'A repair workshop.' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Reserve' }));

    await screen.findByText(/Your reservation is confirmed/);
    const postCall = apiFetch.mock.calls.find(
      ([url, opts]) => /\/request\//.test(url) && opts?.method === 'POST'
    );
    const body = JSON.parse(postCall[1].body);
    expect(body).toEqual({
      start_date: '2026-06-03',
      start_time: '11:00',
      end_time: '13:00',
      project_note: 'A repair workshop.',
      collection_code: 'COL001',
    });
    expect(body.duration_days).toBeUndefined();
  });

  test('changing the day resets an already-chosen duration and start time', async () => {
    setApi({ thing: HOURLY_RESERVE_THING });
    const { container } = renderPage();
    await screen.findByText(/Reserve Sala amb hores/);

    typeHourlyPickup(container, '03/06/2026');
    fireEvent.click(await screen.findByRole('radio', { name: '2 hours' }));
    fireEvent.click(await screen.findByRole('radio', { name: '11:00' }));

    typeHourlyPickup(container, '04/06/2026'); // Thursday, same schedule
    await waitFor(() => expect(screen.queryByRole('radio', { name: '11:00' })).toBeNull());
    expect(screen.queryByRole('radio', { checked: true })).toBeNull();
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

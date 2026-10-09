import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router';
import { vi, describe, test, expect, beforeEach, afterEach } from 'vitest';
import en from '../i18n/locales/en.json';
import es from '../i18n/locales/es.json';
import ca from '../i18n/locales/ca.json';

window.scrollTo = vi.fn();

// The real error readers (apiErrorMessage & co.) are kept: the join-the-group notice is
// built from a coded refusal.
vi.mock('../services/api', async (importOriginal) => ({
  ...(await importOriginal()),
  apiFetch: vi.fn(() =>
    Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) })
  ),
  extractApiError: vi.fn(() => Promise.resolve('')),
  getCsrfToken: vi.fn(() => 'mock-csrf'),
}));

import { apiFetch } from '../services/api';
import RequestThingPage from '../pages/RequestThingPage';

/**
 * The request page says, before the press, that whoever runs the thing is sent the
 * requester's name and email with the request (the server's emails say the same from the
 * other side). The words are fixed letter by letter; the page does not show the
 * address — it has no user and earns no extra request for it.
 */
const APPROVED = {
  request: {
    es: 'Quien gestiona esta cosa verá tu nombre y tu email.',
    ca: 'Qui gestiona aquesta cosa veurà el teu nom i el teu email.',
    en: 'Whoever runs this thing will see your name and email.',
  },
  reservation: {
    es: 'Quien gestiona esto verá tu nombre y tu email.',
    ca: 'Qui gestiona això veurà el teu nom i el teu email.',
    en: 'Whoever runs this will see your name and email.',
  },
};

function mockResponse(data, ok = true) {
  return { ok, status: ok ? 200 : 400, json: () => Promise.resolve(data) };
}

const LEND_THING = {
  code: 'LEND01',
  type: 'LEND_THING',
  headline: 'Ladder',
  fee: null,
  collection_code: 'COL001',
  available_today: true,
  next_available: null,
};

const RESERVE_THING = {
  code: 'RSV01',
  type: 'RESERVE_THING',
  headline: 'Sala polivalent',
  fee: null,
  collection_code: 'COL001',
  rental_weekdays: [],
  reservation_max_days: 1,
  available_today: true,
  next_available: null,
};

function setApi(thing, { request } = {}) {
  apiFetch.mockImplementation((url, opts = {}) => {
    if (/\/collections\/COL001\/join\//.test(url) && opts.method === 'POST') {
      return Promise.resolve(request?.join ?? mockResponse({ message: 'Joined' }));
    }
    if (/\/things\/[^/]+\/request\//.test(url) && opts.method === 'POST') {
      return Promise.resolve(request?.post ?? mockResponse({ booking_code: 'B1' }));
    }
    if (/\/things\/[^/]+\/calendar\//.test(url)) return Promise.resolve(mockResponse([]));
    if (/\/things\/[^/]+\/(\?.*)?$/.test(url)) return Promise.resolve(mockResponse(thing));
    return Promise.resolve(mockResponse({}));
  });
}

function renderPage(thing) {
  return render(
    <MemoryRouter
      initialEntries={[{ pathname: `/collections/COL001/things/${thing.code}/request`, state: {} }]}
    >
      <Routes>
        <Route path="/collections/:code/things/:thingCode/request" element={<RequestThingPage />} />
        <Route path="*" element={<div data-testid="navigated" />} />
      </Routes>
    </MemoryRouter>
  );
}

function typePickup(container, display) {
  const input = container.querySelector('#reservation-pickup-date');
  fireEvent.change(input, { target: { value: display } });
  fireEvent.blur(input);
}

const NOT_A_MEMBER = {
  ok: false,
  status: 403,
  json: () =>
    Promise.resolve({
      error: 'You need to be a member of this group to reserve.',
      code: 'not_a_member',
    }),
};

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem('userCode', 'ABC123');
  localStorage.setItem('koro', 'basic');
  vi.clearAllMocks();
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(new Date(2026, 5, 1, 12, 0, 0)); // Mon 2026-06-01
});

afterEach(() => {
  vi.useRealTimers();
});

describe('RequestThingPage — who will see the requester’s name and email', () => {
  test('a request says so, in the line directly above the button that sends it', async () => {
    setApi(LEND_THING);
    renderPage(LEND_THING);
    await screen.findByText(/Request: Ladder/);

    const sentence = screen.getByText(APPROVED.request.en);
    expect(sentence.tagName).toBe('P');
    // Just above the submit button, in the form's final grid.
    expect(sentence.nextElementSibling).toBe(screen.getByRole('button', { name: 'Borrow' }));
    // The reservation's wording is not this page's.
    expect(screen.queryByText(APPROVED.reservation.en)).toBeNull();
  });

  test('a reservation says so in its own words, above the Reserve button', async () => {
    setApi(RESERVE_THING);
    renderPage(RESERVE_THING);
    await screen.findByText(/Reserve Sala polivalent/);

    const sentence = screen.getByText(APPROVED.reservation.en);
    expect(sentence.tagName).toBe('P');
    expect(sentence.nextElementSibling).toBe(screen.getByRole('button', { name: 'Reserve' }));
    expect(screen.queryByText(APPROVED.request.en)).toBeNull();
  });

  test('it does not show the address — the page does not hold one', async () => {
    setApi(LEND_THING);
    renderPage(LEND_THING);
    await screen.findByText(/Request: Ladder/);

    expect(screen.getByText(APPROVED.request.en)).not.toHaveTextContent('@');
    // …and asks for nothing more to be able to: the thing, and its calendar.
    const urls = apiFetch.mock.calls.map(([url]) => url);
    expect(urls.filter((url) => /auth\/me|users\//.test(url))).toEqual([]);
  });

  test('it is not in the join-the-group notice, which stands apart from the form', async () => {
    setApi(RESERVE_THING, { request: { join: { ok: false, status: 500 }, post: NOT_A_MEMBER } });
    const { container } = renderPage(RESERVE_THING);
    await screen.findByText(/Reserve Sala polivalent/);

    typePickup(container, '03/06/2026');
    fireEvent.click(screen.getByRole('button', { name: 'Reserve' }));

    const nudge = await waitFor(() => {
      const found = container.querySelector('.invite-nudge');
      expect(found).not.toBeNull();
      return found;
    });
    expect(nudge).not.toHaveTextContent(APPROVED.reservation.en);
    expect(nudge).not.toHaveTextContent(APPROVED.request.en);
    // It is still the form's, once.
    expect(screen.getAllByText(APPROVED.reservation.en)).toHaveLength(1);
  });

  test('it is gone once the request has gone: the success branch does not repeat it', async () => {
    setApi(RESERVE_THING);
    const { container } = renderPage(RESERVE_THING);
    await screen.findByText(/Reserve Sala polivalent/);

    typePickup(container, '03/06/2026');
    fireEvent.click(screen.getByRole('button', { name: 'Reserve' }));

    expect(await screen.findByText(/Your reservation is confirmed/)).toBeInTheDocument();
    expect(screen.queryByText(APPROVED.reservation.en)).toBeNull();
    expect(screen.queryByText(APPROVED.request.en)).toBeNull();
  });
});

describe('the two sentences are in the three locales as approved', () => {
  const locales = { en, es, ca };

  for (const [language, locale] of Object.entries(locales)) {
    test(`${language}: request.contactShared and reservation.contactShared`, () => {
      expect(locale.request.contactShared).toBe(APPROVED.request[language]);
      expect(locale.reservation.contactShared).toBe(APPROVED.reservation[language]);
    });
  }
});

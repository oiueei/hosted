import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route, useLocation } from 'react-router';
import { vi, describe, test, expect, beforeEach } from 'vitest';

/**
 * What `UserPage` does around the happy path of a profile that loads: how it fails,
 * how the own profile finds out who it is, what the "leave" link hands the next page,
 * and what another member's profile shows. `myGroups.test.jsx` (the list itself, its
 * failure never taking the profile down) and `userPageTitle.test.jsx` cover the rest.
 */

window.scrollTo = vi.fn();

vi.mock('../services/api', () => ({
  apiFetch: vi.fn(),
  getCsrfToken: vi.fn(() => 'mock-csrf'),
}));

import en from '../i18n/locales/en.json';
import { apiFetch } from '../services/api';
import UserPage from '../pages/UserPage';

const ok = (body) => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });
const refused = (status) => Promise.resolve({ ok: false, status, json: async () => ({}) });

const ME = { code: 'ME0001', name: 'Carlos', email: 'me@test.com', created: '2026-01-01' };
const OTHER = {
  code: 'OTH001',
  name: 'Lili',
  email: 'lili@test.com',
  created: '2026-01-01',
  shared_collections: [],
};

beforeEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
});

const renderAt = (path) =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/me" element={<UserPage />} />
        <Route path="/:userCode" element={<UserPage />} />
        <Route path="/collections/:code/leave" element={<LeaveProbe />} />
      </Routes>
    </MemoryRouter>
  );

// Stands in for LeaveCollectionPage: shows what the link handed it in navigation state.
function LeaveProbe() {
  const { state } = useLocation();
  return <p>leaving: {state?.headline}</p>;
}

describe('UserPage when the profile does not load', () => {
  beforeEach(() => {
    localStorage.setItem('userCode', 'ME0001');
  });

  test.each([
    [403, en.userPage.noPermission],
    [404, en.userPage.notFound],
    [500, en.userPage.errorLoading],
  ])('a %i says why', async (status, message) => {
    apiFetch.mockImplementation(() => refused(status));

    renderAt('/OTH001');

    expect(await screen.findByText(message)).toBeInTheDocument();
    // A dead end is not an answer: the way back is there (DESIGN A1).
    expect(screen.getByRole('link', { name: en.common.home })).toHaveAttribute('href', '/');
  });

  test('a request that never arrives says the connection is down', async () => {
    apiFetch.mockImplementation(() => Promise.reject(new Error('offline')));

    renderAt('/OTH001');

    expect(await screen.findByText(en.common.connectionError)).toBeInTheDocument();
  });
});

describe('UserPage on /me without a stored userCode', () => {
  test('asks the server who the visitor is, remembers the answer, and shows the profile', async () => {
    apiFetch.mockImplementation((url) => (url === '/api/v1/auth/me/' ? ok(ME) : ok([])));

    renderAt('/me');

    expect(await screen.findByRole('heading', { name: 'Carlos' })).toBeInTheDocument();
    // Everything else in the app finds "who is signed in" in this one key.
    expect(localStorage.getItem('userCode')).toBe('ME0001');
    // It is the own profile, so it carries the own-profile actions.
    expect(screen.getByRole('link', { name: /edit profile/i })).toHaveAttribute('href', '/me/edit');
    // It is what the page asked first, before it knew any code to ask about.
    expect(apiFetch.mock.calls[0][0]).toBe('/api/v1/auth/me/');
  });

  test('a refusal there says the profile could not be loaded, and stores nothing', async () => {
    apiFetch.mockImplementation((url) => (url === '/api/v1/auth/me/' ? refused(401) : ok([])));

    renderAt('/me');

    expect(await screen.findByText(en.userPage.errorLoading)).toBeInTheDocument();
    expect(localStorage.getItem('userCode')).toBeNull();
  });
});

describe('UserPage — leaving a group from the own profile', () => {
  test('the link hands the next page the group name in the reader’s language, not raw JSON', async () => {
    localStorage.setItem('userCode', 'ME0001');
    apiFetch.mockImplementation((url) =>
      url.startsWith('/api/v1/invited-collections/')
        ? ok([{ code: 'COL003', headline: '{"en": "Mum\'s things", "es": "Las cosas de mamá"}' }])
        : ok(ME)
    );
    renderAt('/me');

    fireEvent.click(await screen.findByRole('link', { name: /leave the group/i }));

    // The confirmation page names the group from this state (a refresh loses it and
    // it falls back to a generic word), so what is handed over must already be words.
    await waitFor(() => expect(screen.getByText("leaving: Mum's things")).toBeInTheDocument());
  });
});

describe('UserPage — another member’s profile', () => {
  beforeEach(() => {
    localStorage.setItem('userCode', 'ME0001');
  });

  test('lists the collections the two share, and offers no own-profile actions', async () => {
    apiFetch.mockImplementation(() =>
      ok({
        ...OTHER,
        shared_collections: [
          { code: 'COL001', headline: "Lili's Lending Library" },
          { code: 'COL002', headline: '{"en": "Leafy Lounge", "es": "Salón verde"}' },
        ],
      })
    );

    renderAt('/OTH001');

    expect(
      await screen.findByRole('heading', { name: en.userPage.collectionsInCommon })
    ).toBeInTheDocument();
    expect(screen.getByText("Lili's Lending Library")).toBeInTheDocument();
    expect(screen.getByText('Leafy Lounge')).toBeInTheDocument();
    expect(screen.queryByText(/\{"en"/)).not.toBeInTheDocument();
    // These are hers: editing them, or signing out, is not on offer here.
    expect(screen.queryByRole('link', { name: /edit profile/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /log ?out/i })).not.toBeInTheDocument();
    // ...and the "you share nothing" line must not appear next to a list of what they share.
    expect(screen.queryByText(/don't share any collections/i)).not.toBeInTheDocument();
  });

  test('a profile with nothing in common says so by name', async () => {
    apiFetch.mockImplementation(() => ok(OTHER));

    renderAt('/OTH001');

    expect(
      await screen.findByText("You and Lili don't share any collections yet.")
    ).toBeInTheDocument();
  });

  test('a profile with an About text does not add the empty-state line', async () => {
    apiFetch.mockImplementation(() => ok({ ...OTHER, about: 'I like **bikes**.' }));

    renderAt('/OTH001');

    expect(
      await screen.findByRole('heading', { name: en.userPage.aboutHeading })
    ).toBeInTheDocument();
    expect(screen.getByText('bikes').tagName).toBe('STRONG');
    expect(screen.queryByText(/don't share any collections/i)).not.toBeInTheDocument();
  });
});

describe('UserPage — the photo', () => {
  beforeEach(() => {
    localStorage.setItem('userCode', 'ME0001');
  });

  test('is described by the member’s name, or by their email when they gave none', async () => {
    apiFetch.mockImplementation(() => ok({ ...OTHER, photo_url: 'https://cdn.example/lili.jpg' }));
    const { unmount } = renderAt('/OTH001');
    expect(await screen.findByRole('img', { name: 'Photo of Lili' })).toHaveAttribute(
      'src',
      'https://cdn.example/lili.jpg'
    );
    unmount();

    apiFetch.mockImplementation(() =>
      ok({ ...OTHER, name: '', photo_url: 'https://cdn.example/lili.jpg' })
    );
    renderAt('/OTH001');
    expect(await screen.findByRole('img', { name: 'Photo of lili@test.com' })).toBeInTheDocument();
  });

  test('a member with no photo gets no empty image', async () => {
    apiFetch.mockImplementation(() => ok(OTHER));

    renderAt('/OTH001');

    await screen.findByRole('heading', { name: 'Lili' });
    expect(screen.queryByRole('img')).not.toBeInTheDocument();
  });
});

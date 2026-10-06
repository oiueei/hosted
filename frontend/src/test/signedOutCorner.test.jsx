import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router';
import { vi, describe, test, expect, beforeEach } from 'vitest';

/**
 * The "Sign in" icon in the hero's corner is every signed-out
 * reader's, on almost every page — except where the hero already offers "Sign in" as
 * a button of its own: a PUBLIC collection. These tests pin the
 * other side of that rule, which `CollectionPage.test.jsx` cannot: the page of a
 * *thing* in the same public group keeps the icon, and so does `/legal`, because
 * the switch (`AccountMenu`'s `offerSignIn`) is the collection page's, not the app's.
 */
window.scrollTo = vi.fn();

vi.mock('../services/api', async (importOriginal) => ({
  ...(await importOriginal()),
  apiFetch: vi.fn(),
  getCsrfToken: vi.fn(() => 'mock-csrf'),
}));
vi.mock('../hooks/useCollectionLanguage', () => ({ default: vi.fn() }));

import { apiFetch } from '../services/api';
import ThingPage from '../pages/ThingPage';
import CollectionPage from '../pages/CollectionPage';
import LegalPage from '../pages/LegalPage';

const ok = (body) => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });

const THING = {
  code: 'THG001',
  headline: 'Kettle',
  description: 'Steel.',
  type: 'GIFT_THING',
  status: 'ACTIVE',
  owner: 'OWN001',
  owner_name: 'Lili',
  created: '2026-07-01T10:00:00Z',
  thumbnail_url: '',
  gallery_urls: [],
  tags: [],
  collection_code: 'COL001',
  collection_language: '',
  available_today: true,
  next_available: null,
};

const PUBLIC_COLLECTION = {
  code: 'COL001',
  headline: 'Kitchen Collection',
  description: 'Things from the kitchen',
  status: 'ACTIVE',
  visibility: 'PUBLIC',
  mode: 'PROPRIETARY',
  owner: 'OWN001',
  owner_name: 'Lili',
  is_curator: false,
  is_member: false,
  co_owners: [],
  thumbnail_url: '',
  tags: [],
  things: [],
  invites: [],
  is_paused: false,
  allowed_thing_types: [],
  digest_frequency: 'NONE',
  allow_member_proposals: false,
};

beforeEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
  apiFetch.mockImplementation((url) => {
    if (url.includes('/transfers/')) return ok({ total_transfers: 0, transfers: [] });
    if (url.includes('/faq/')) return ok({ results: [] });
    if (url.includes('/calendar/')) return ok([]);
    if (url.includes('/things/')) return ok(THING);
    if (url.includes('/inbox/')) return ok([]);
    if (url.includes('/collections/')) return ok(PUBLIC_COLLECTION);
    return ok({});
  });
});

const cornerLinks = (container) =>
  [...container.querySelectorAll('.hero-corners a')].map((a) => [
    a.getAttribute('aria-label'),
    a.getAttribute('href'),
  ]);

describe('the corner of a reader with no session', () => {
  test('a public collection leaves the icon out: the hero has the button', async () => {
    const { container } = render(
      <MemoryRouter initialEntries={['/collections/COL001']}>
        <Routes>
          <Route path="/collections/:code" element={<CollectionPage />} />
        </Routes>
      </MemoryRouter>
    );
    await screen.findByText('Things from the kitchen');

    expect(cornerLinks(container)).toEqual([]);
    expect(screen.getByRole('link', { name: 'Sign in' })).toHaveAttribute(
      'href',
      '/login?next=%2Fcollections%2FCOL001'
    );
  });

  test('a thing in that same public group keeps it', async () => {
    const { container } = render(
      <MemoryRouter initialEntries={['/collections/COL001/things/THG001']}>
        <Routes>
          <Route path="/collections/:code/things/:thingCode" element={<ThingPage />} />
        </Routes>
      </MemoryRouter>
    );
    await screen.findByRole('heading', { level: 1, name: 'Kettle' });

    expect(cornerLinks(container)).toEqual([
      ['Sign in', '/login?next=%2Fcollections%2FCOL001%2Fthings%2FTHG001'],
    ]);
  });

  test('the standalone page of a thing keeps it too', async () => {
    const { container } = render(
      <MemoryRouter initialEntries={['/things/THG001']}>
        <Routes>
          <Route path="/things/:thingCode" element={<ThingPage />} />
        </Routes>
      </MemoryRouter>
    );
    await screen.findByRole('heading', { level: 1, name: 'Kettle' });

    expect(cornerLinks(container)).toEqual([['Sign in', '/login?next=%2Fthings%2FTHG001']]);
  });

  test('/legal keeps it', async () => {
    const { container } = render(
      <MemoryRouter initialEntries={['/legal']}>
        <Routes>
          <Route path="/legal" element={<LegalPage />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() =>
      expect(cornerLinks(container)).toEqual([['Sign in', '/login?next=%2Flegal']])
    );
  });
});

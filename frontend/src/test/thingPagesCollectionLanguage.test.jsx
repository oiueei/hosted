import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router';
import { vi, describe, test, expect, beforeEach } from 'vitest';

/**
 * The two thing pages a member lands on most — `ThingPage`, where a magic link
 * drops them after joining to act (S13), and `RequestThingPage` — learn their
 * collection's language only from the thing itself (`collection_language` on
 * `/things/{code}/`), since neither fetches the collection. `SharePage`,
 * `CollectionPage` and `EditCollectionPage` each pin their own wire into
 * `useCollectionLanguage`; these two had none. The hook is tested on its own
 * (`useCollectionLanguage.test.jsx`) — what can break here is the call: a
 * wrong field, and a Catalan group's things quietly show English chrome; the
 * owner's texts left out, and an owner who wrote in the visitor's language
 * no longer keeps them in it.
 */

window.scrollTo = vi.fn();

vi.mock('../services/api', async (importOriginal) => ({
  ...(await importOriginal()),
  apiFetch: vi.fn(),
  getCsrfToken: vi.fn(() => 'mock-csrf'),
}));
vi.mock('../hooks/useCollectionLanguage', () => ({ default: vi.fn() }));

import { apiFetch } from '../services/api';
import useCollectionLanguage from '../hooks/useCollectionLanguage';
import ThingPage from '../pages/ThingPage';
import RequestThingPage from '../pages/RequestThingPage';

const ok = (body) => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });

// The subset of `ThingSerializer`'s output these pages read, with the owner's
// headline written in two languages — raw, as the API serves it.
const HEADLINE = '{"ca": "Sala del casal", "es": "Sala del centro"}';
const DESCRIPTION = 'Amb projector.';
const THING = {
  code: 'THG001',
  headline: HEADLINE,
  description: DESCRIPTION,
  type: 'LEND_THING',
  status: 'ACTIVE',
  owner: 'OWN001',
  owner_name: 'Lili',
  created: '2026-07-01T10:00:00Z',
  thumbnail_url: '',
  gallery_urls: [],
  tags: [],
  collection_code: 'COL001',
  collection_language: 'ca',
  available_today: true,
  next_available: null,
};

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem('userCode', 'SOMEBODY');
  vi.clearAllMocks();
  apiFetch.mockImplementation((url) => {
    if (url.includes('/transfers/')) return ok({ total_transfers: 0, transfers: [] });
    if (url.includes('/faq/')) return ok({ results: [] });
    if (url.includes('/calendar/')) return ok([]);
    if (url.includes('/things/')) return ok(THING);
    return ok({});
  });
});

const renderAt = (path, routePath, page) =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path={routePath} element={page} />
      </Routes>
    </MemoryRouter>
  );

describe("the thing pages hand useCollectionLanguage their collection's language", () => {
  test('ThingPage', async () => {
    renderAt(
      '/collections/COL001/things/THG001',
      '/collections/:code/things/:thingCode',
      <ThingPage />
    );

    // An English reader gets the owner's Spanish (en → es → first written).
    await screen.findAllByText(/Sala del centro/);
    await waitFor(() =>
      expect(useCollectionLanguage).toHaveBeenLastCalledWith('ca', [HEADLINE, DESCRIPTION])
    );
  });

  test('RequestThingPage', async () => {
    renderAt(
      '/collections/COL001/things/THG001/request',
      '/collections/:code/things/:thingCode/request',
      <RequestThingPage />
    );

    await waitFor(() =>
      expect(useCollectionLanguage).toHaveBeenLastCalledWith('ca', [HEADLINE, DESCRIPTION])
    );
  });
});

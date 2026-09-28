import { render, waitFor } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router';
import { vi, describe, test, expect, beforeEach } from 'vitest';

/**
 * `ThingPage` used to fetch `/things/{code}/` bare, so the server resolved the
 * collection itself (`_viewable_collection`'s first hit): a thing living in two
 * collections could show `available_today`, `next_available` and `can_manage`
 * computed under the *other* collection's rules — while `RequestThingPage`,
 * one click away, already asked for the collection in the URL. What this pins
 * is the wire: on `/collections/:code/things/:thingCode` the thing fetch
 * carries `?collection=`, on the standalone route it carries nothing, moving
 * between two collections of the same thing refetches through the new one, and
 * the transfers fetch never grows the parameter (that endpoint doesn't take
 * one). `thingPagesCollectionLanguage.test.jsx` pins the language half of the
 * same fetch.
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

const ok = (body) => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });

const THING = {
  code: 'THG001',
  headline: 'Sala gran',
  description: 'Amb projector.',
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

const mountAt = (path) => {
  const router = createMemoryRouter(
    [{ path: '/collections/:code/things/:thingCode', element: <ThingPage /> }],
    { initialEntries: [path] }
  );
  render(<RouterProvider router={router} />);
  return router;
};

const calledUrls = () => apiFetch.mock.calls.map((call) => call[0]);

describe('ThingPage reads a thing through the collection in its URL', () => {
  test('the collection-context route asks for that collection', async () => {
    mountAt('/collections/COL001/things/THG001');

    await waitFor(() => expect(calledUrls()).toContain('/api/v1/things/THG001/?collection=COL001'));
  });

  test('the standalone route asks for no collection', async () => {
    const router = createMemoryRouter([{ path: '/things/:thingCode', element: <ThingPage /> }], {
      initialEntries: ['/things/THG001'],
    });
    render(<RouterProvider router={router} />);

    await waitFor(() => expect(calledUrls()).toContain('/api/v1/things/THG001/'));
    expect(calledUrls().some((url) => url.includes('?collection='))).toBe(false);
  });

  test('moving to another collection of the same thing refetches through it', async () => {
    const router = mountAt('/collections/COL001/things/THG001');
    await waitFor(() => expect(calledUrls()).toContain('/api/v1/things/THG001/?collection=COL001'));

    await router.navigate('/collections/COL002/things/THG001');

    await waitFor(() => expect(calledUrls()).toContain('/api/v1/things/THG001/?collection=COL002'));
  });

  test('the transfers fetch never carries the parameter', async () => {
    const router = mountAt('/collections/COL001/things/THG001');
    await waitFor(() => expect(calledUrls()).toContain('/api/v1/things/THG001/?collection=COL001'));
    await router.navigate('/collections/COL002/things/THG001');
    await waitFor(() => expect(calledUrls()).toContain('/api/v1/things/THG001/?collection=COL002'));

    const transferUrls = calledUrls().filter((url) => url.includes('/transfers/'));
    expect(transferUrls.length).toBeGreaterThan(0);
    expect(transferUrls.every((url) => url === '/api/v1/things/THG001/transfers/')).toBe(true);
  });
});

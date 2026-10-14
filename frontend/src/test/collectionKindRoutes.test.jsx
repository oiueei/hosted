import { render, screen, waitFor } from '@testing-library/react';
import { vi, describe, test, expect, beforeEach, afterEach } from 'vitest';
import { COLLECTION_PREFIXES } from '../utils/collectionPath';

/**
 * A collection's pages are mounted once per prefix — `/stall`, `/library`, `/shed`
 * and the old `/collections` — from one list in `App.jsx`. Only the whole App can
 * say each of them is in the route table, behind `RequireAuth` where it is
 * protected, and that an old address is moved to its kind's.
 */
const LIBRARY = {
  code: 'COL001',
  kind: 'LIBRARY',
  headline: 'The lending library',
  status: 'ACTIVE',
  visibility: 'PUBLIC',
  mode: 'PROPRIETARY',
  owner: 'USR999',
  owner_name: 'Lele',
  is_curator: false,
  tags: [],
  things: [],
  invites: [],
  co_owners: [],
  allowed_thing_types: ['LEND_THING', 'RENT_THING'],
};

globalThis.fetch = vi.fn((url) => {
  const collection = String(url).includes('/api/v1/collections/COL001/');
  return Promise.resolve({
    ok: collection,
    status: collection ? 200 : 401,
    json: () => Promise.resolve(collection ? LIBRARY : {}),
  });
});
window.scrollTo = vi.fn();

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem('userCode', 'USR001');
  vi.clearAllMocks();
  vi.resetModules();
});

afterEach(() => {
  window.history.pushState({}, '', '/');
});

const openApp = async (path) => {
  window.history.pushState({}, '', path);
  const { default: App } = await import('../App');
  render(<App />);
};

describe('every prefix mounts the collection’s pages', () => {
  test.each(COLLECTION_PREFIXES)('/%s/COL001/import is the import page', async (prefix) => {
    await openApp(`/${prefix}/COL001/import`);

    expect(
      await screen.findByRole('heading', { level: 1, name: 'Add several at once (CSV)' })
    ).toBeVisible();
  });

  test.each(['stall', 'library', 'shed', 'collections'])(
    '/%s/COL001/invites/import is behind the sign-in',
    async (prefix) => {
      localStorage.clear();
      await openApp(`/${prefix}/COL001/invites/import`);

      await waitFor(() => expect(window.location.pathname).toBe('/login'));
      expect(new URLSearchParams(window.location.search).get('next')).toBe(
        `/${prefix}/COL001/invites/import`
      );
    }
  );

  test('the public page of the right prefix paints the collection and stays put', async () => {
    await openApp('/library/COL001');

    expect(await screen.findByRole('heading', { level: 1, name: /lending library/ })).toBeVisible();
    expect(window.location.pathname).toBe('/library/COL001');
  });
});

describe('starting a collection', () => {
  test('/new is the chooser: three kinds, no form', async () => {
    await openApp('/new');

    expect(await screen.findAllByRole('listitem')).toHaveLength(3);
    expect(screen.queryByLabelText(/^Title/)).toBeNull();
  });

  test.each(['stall', 'library', 'shed'])('/%s/new is the form', async (prefix) => {
    await openApp(`/${prefix}/new`);

    expect(await screen.findByLabelText(/^Title/)).toBeVisible();
    expect(window.location.pathname).toBe(`/${prefix}/new`);
  });
});

describe('the address from before kinds', () => {
  test.each(['/collections/COL001', '/stall/COL001', '/shed/COL001'])(
    '%s lands on /library/COL001 once the kind is known',
    async (path) => {
      await openApp(path);

      await waitFor(() => expect(window.location.pathname).toBe('/library/COL001'));
    }
  );

  test('the join page keeps the thing it was opened for', async () => {
    await openApp('/collections/COL001/join?thing=XyZ789');

    await waitFor(() => expect(window.location.pathname).toBe('/library/COL001/join'));
    expect(window.location.search).toBe('?thing=XyZ789');
  });

  test('/collections/new is the new-collection page at /new', async () => {
    await openApp('/collections/new');

    await waitFor(() => expect(window.location.pathname).toBe('/new'));
  });

  test.each(['/stall', '/library', '/shed'])('%s leads on to its own form', async (path) => {
    await openApp(path);

    await waitFor(() => expect(window.location.pathname).toBe(`${path}/new`));
  });
});

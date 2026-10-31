import { render, screen } from '@testing-library/react';
import { vi, describe, test, expect, beforeEach, afterEach } from 'vitest';

/**
 * A code is six capitals and digits, and two sub-routes of a collection are six
 * letters: `delete` and `import`. React Router ignores case unless a route says
 * otherwise, so `/library/ABC123/DELETE` — a person whose code is `DELETE` — opened
 * the page that deletes the collection. Every sub-route of a collection is
 * case-sensitive; only the whole App can say so, since it is the route table that
 * decides.
 */
globalThis.fetch = vi.fn((url) => {
  const collection = String(url).includes('/api/v1/collections/COL001/');
  return Promise.resolve({
    ok: collection,
    status: collection ? 200 : 401,
    json: () =>
      Promise.resolve(
        collection
          ? { code: 'COL001', headline: 'The lending library', kind: 'LIBRARY', things: [] }
          : {}
      ),
  });
});
window.scrollTo = vi.fn();

async function openApp(path) {
  localStorage.setItem('userCode', 'USR001');
  window.history.pushState({}, '', path);
  const { default: App } = await import('../App');
  render(<App />);
}

beforeEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
  vi.resetModules();
});

afterEach(() => {
  window.history.pushState({}, '', '/');
});

describe('the sub-routes of a collection tell case apart', () => {
  test('the lowercase sub-route is the page that deletes it', async () => {
    await openApp('/library/COL001/delete');

    expect(await screen.findByRole('heading', { level: 1, name: /Delete/ })).toBeVisible();
  });

  test.each(['DELETE', 'IMPORT', 'Delete'])(
    '%s is not the page that deletes or imports: it is the collection, as a code that names nobody',
    async (segment) => {
      await openApp(`/library/COL001/${segment}`);

      expect(
        await screen.findByRole('heading', { level: 1, name: 'The lending library' })
      ).toBeVisible();
      expect(screen.queryByRole('heading', { name: /Delete/ })).toBeNull();
      expect(screen.queryByRole('heading', { name: 'Add several at once (CSV)' })).toBeNull();
    }
  );

  test('the lowercase import is still the import page', async () => {
    await openApp('/library/COL001/import');

    expect(
      await screen.findByRole('heading', { level: 1, name: 'Add several at once (CSV)' })
    ).toBeVisible();
  });

  test('the public sub-routes tell case apart too', async () => {
    await openApp('/library/COL001/JOIN');

    expect(
      await screen.findByRole('heading', { level: 1, name: 'The lending library' })
    ).toBeVisible();
    expect(screen.queryByRole('heading', { name: /Join/ })).toBeNull();
  });
});

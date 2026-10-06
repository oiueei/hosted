import { render, screen, waitFor } from '@testing-library/react';
import { vi, describe, test, expect, beforeEach, afterEach } from 'vitest';

/**
 * `/collections/:code/invites/import` is a route of the app, protected like
 * `/invites`. The page's own tests render the page; only the
 * whole App can say the route table has the entry, that it sits behind
 * `RequireAuth`, and that it is not read as the sibling `/invites/remove`.
 */
globalThis.fetch = vi.fn((url) => {
  const collection = String(url).includes('/api/v1/collections/COL001/');
  return Promise.resolve({
    ok: collection,
    status: collection ? 200 : 401,
    json: () =>
      Promise.resolve(collection ? { code: 'COL001', headline: 'The lending library' } : {}),
  });
});
window.scrollTo = vi.fn();

beforeEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
  vi.resetModules();
  window.history.pushState({}, '', '/collections/COL001/invites/import');
});

afterEach(() => {
  window.history.pushState({}, '', '/');
});

describe('the invitations import route', () => {
  test('a signed-in reader gets the import page, not the members list', async () => {
    localStorage.setItem('userCode', 'USR001');
    const { default: App } = await import('../App');
    render(<App />);

    expect(
      await screen.findByRole('heading', { level: 1, name: 'Invite many at once (CSV)' })
    ).toBeVisible();
    expect(window.location.pathname).toBe('/collections/COL001/invites/import');
    // The page of the one-at-a-time form is a different route.
    expect(screen.queryByLabelText('Guest email')).toBeNull();
  });

  test('a reader with no session is sent to sign in, and brought back to it', async () => {
    const { default: App } = await import('../App');
    render(<App />);

    await waitFor(() => expect(window.location.pathname).toBe('/login'));
    expect(new URLSearchParams(window.location.search).get('next')).toBe(
      '/collections/COL001/invites/import'
    );
    expect(screen.queryByRole('heading', { name: 'Invite many at once (CSV)' })).toBeNull();
  });
});

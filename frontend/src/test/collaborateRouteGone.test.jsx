import { render, screen } from '@testing-library/react';
import { vi, describe, test, expect, beforeEach, afterEach } from 'vitest';

/**
 * `/collaborate` left the front end (the app is simpler without it; to be rethought). The only way in was a link under `/contact`'s
 * form, and that went too. There is no redirect and no route of its own: the path
 * is a single segment like any other unknown one, so it is read as a profile code
 * — the signed-in reader lands on `UserPage`'s own "User not found.", as `/shared`
 * does (`sharedRouteGone.test.jsx`). This renders the whole App at the old path,
 * because the route table is what had to lose the entry and only the whole App can
 * say so.
 */
const asked = [];
globalThis.fetch = vi.fn((url) => {
  asked.push(String(url));
  const notFound = String(url).includes('/api/v1/users/collaborate/');
  return Promise.resolve({
    ok: false,
    status: notFound ? 404 : 401,
    json: () => Promise.resolve({}),
  });
});
window.scrollTo = vi.fn();

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem('userCode', 'USR001');
  asked.length = 0;
  vi.clearAllMocks();
  vi.resetModules();
  window.history.pushState({}, '', '/collaborate');
});

afterEach(() => {
  window.history.pushState({}, '', '/');
});

describe('the retired /collaborate path', () => {
  test('a signed-in reader gets "not found", not the collaboration form and not a redirect', async () => {
    const { default: App } = await import('../App');
    render(<App />);

    expect(await screen.findByText('User not found.')).toBeVisible();
    expect(screen.queryByText('Collaborate with OIUEEI')).toBeNull();
    expect(screen.queryByRole('textbox', { name: /message/i })).toBeNull();
    expect(window.location.pathname).toBe('/collaborate');
    // It is asked for like any profile code: the contact endpoint is not involved.
    expect(asked.filter((url) => url.includes('/api/v1/contact/'))).toEqual([]);
  });
});

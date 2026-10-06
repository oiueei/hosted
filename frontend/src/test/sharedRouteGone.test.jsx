import { render, screen } from '@testing-library/react';
import { vi, describe, test, expect, beforeEach, afterEach } from 'vitest';

/**
 * `/shared` ("Shared with me") left the front end. There is no redirect and no route of its own: the path is a single
 * segment like any other unknown one, so it is read as a profile code, the way
 * `/anything` is — the signed-in reader lands on `UserPage`'s own "User not
 * found." This renders the whole App at the old path, because the route table is
 * what had to lose the entry and only the whole App can say so.
 */
const asked = [];
globalThis.fetch = vi.fn((url) => {
  asked.push(String(url));
  const notFound = String(url).includes('/api/v1/users/shared/');
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
  window.history.pushState({}, '', '/shared');
});

afterEach(() => {
  window.history.pushState({}, '', '/');
});

describe('the retired /shared path', () => {
  test('a signed-in reader gets "not found", not a list of shared things and not a redirect', async () => {
    const { default: App } = await import('../App');
    render(<App />);

    expect(await screen.findByText('User not found.')).toBeVisible();
    expect(screen.queryByRole('heading', { name: /shared with me/i })).toBeNull();
    expect(window.location.pathname).toBe('/shared');
    // And nothing asks the API for the endpoint that fed it.
    expect(asked.filter((url) => url.includes('invited-things'))).toEqual([]);
  });
});

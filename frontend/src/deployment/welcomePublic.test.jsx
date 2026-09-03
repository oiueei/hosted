import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { vi, describe, test, expect, beforeEach, afterEach } from 'vitest';

vi.mock('../services/api', () => ({
  apiFetch: vi.fn(),
  getCsrfToken: () => 'tok',
}));

import { apiFetch } from '../services/api';
import './testI18n';
import WelcomePage from './pages/WelcomePage';
import { nestedTabStops } from '../test/nestedInteractive';

// /welcome is the page that explains what OIUEEI is — the one you send to
// somebody who has never heard of it. It sits in the public route block, but it
// was unusable signed out: its two `apiFetch` calls 401'd, and apiFetch's own
// logout redirect fired before the page's `.catch()` could swallow anything. The
// stranger got a login form. On top of that every action on the page pointed at
// a RequireAuth route, so even once it rendered, clicking anything bounced them.
//
// These tests pin both halves: it renders for an anonymous visitor, and the
// doors it offers them are ones that actually open.
function renderWelcome() {
  return render(
    <MemoryRouter initialEntries={['/welcome']}>
      <WelcomePage />
    </MemoryRouter>
  );
}

describe('WelcomePage — readable without an account', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  test('an anonymous visitor gets the page, and its calls opt out of the logout redirect', async () => {
    apiFetch.mockResolvedValue({ ok: false, status: 401 });

    renderWelcome();

    expect(await screen.findByText(/Welcome to OIUEEI/i)).toBeInTheDocument();
    await waitFor(() => expect(apiFetch).toHaveBeenCalled());
    // The flag is the whole fix — without it apiFetch navigates to /login from
    // inside the helper and the visitor never sees this page.
    for (const [, options] of apiFetch.mock.calls) {
      expect(options?.optionalAuth).toBe(true);
    }
  });

  test('an anonymous visitor is offered the doors that open, not the protected ones', async () => {
    apiFetch.mockResolvedValue({ ok: false, status: 401 });

    renderWelcome();
    await screen.findByText(/Welcome to OIUEEI/i);

    const hrefs = Array.from(document.querySelectorAll('a')).map((a) => a.getAttribute('href'));
    expect(hrefs).toContain('/popin');
    expect(hrefs).toContain('/login');
    // Every one of these is behind RequireAuth: offering them to a signed-out
    // visitor is a link straight back to the login form they came to avoid.
    expect(hrefs).not.toContain('/collections/new');
    expect(hrefs).not.toContain('/me/edit');
    expect(hrefs).not.toContain('/');
  });

  // This page is deployment-only, so the invariant wired into `smoke.test.jsx`
  // and `a11yInteractive.test.jsx` upstream never reaches it — and it is the page
  // most first-time visitors land on. It carried five `<Link><Button>` pairs of
  // its own until the 2026-08-30 round, two tab stops each, and nothing here
  // would have said so: axe reports no violation for the shape.
  test.each([
    ['an anonymous visitor', null],
    ['a signed-in member', 'USER01'],
  ])('no tab stop contains another, for %s', async (_who, userCode) => {
    if (userCode) localStorage.setItem('userCode', userCode);
    apiFetch.mockResolvedValue({ ok: false, status: 401 });

    const { container } = renderWelcome();
    await screen.findByText(/Welcome to OIUEEI/i);

    expect(nestedTabStops(container)).toEqual([]);
  });

  test('a signed-in member keeps the member actions', async () => {
    localStorage.setItem('userCode', 'USER01');
    apiFetch.mockImplementation((url) =>
      Promise.resolve(
        url.includes('/auth/me/')
          ? { ok: true, json: () => Promise.resolve({ name: 'Lala' }) }
          : { ok: true, json: () => Promise.resolve([]) }
      )
    );

    renderWelcome();
    await screen.findByText(/Welcome to OIUEEI/i);

    const hrefs = Array.from(document.querySelectorAll('a')).map((a) => a.getAttribute('href'));
    expect(hrefs).toContain('/collections/new');
    expect(hrefs).toContain('/me/edit');
    expect(hrefs).not.toContain('/popin');
  });
});

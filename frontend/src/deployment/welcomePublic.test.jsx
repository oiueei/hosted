import { render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { vi, describe, test, expect, beforeEach, afterEach } from 'vitest';

// `FeedbackLink` reads VITE_FEEDBACK_URL once, when its module loads, and this
// file imports WelcomePage statically — so the variable is set here, hoisted
// above the imports, for the "Ideas and bugs" button of the closing row. (With
// no URL the button is simply absent, which `FeedbackLink.test.jsx` pins.)
vi.hoisted(() => {
  vi.stubEnv('VITE_FEEDBACK_URL', 'https://forms.example/feedback');
});
const FEEDBACK_URL = 'https://forms.example/feedback';

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

  test('the hero says "New here?" for the primary door and "Already have an account?" for the secondary', async () => {
    // CA, 2026-10-03: the hero's two buttons for a stranger read as a question
    // and its answer — new here, or already in — each to its own door.
    apiFetch.mockResolvedValue({ ok: false, status: 401 });

    const { container } = renderWelcome();
    await screen.findByText(/Welcome to OIUEEI/i);

    const hero = within(container.querySelector('.form-hero'));
    const newHere = hero.getByRole('link', { name: 'New here?' });
    const haveAccount = hero.getByRole('link', { name: 'Already have an account?' });
    expect(newHere).toHaveAttribute('href', '/popin');
    expect(haveAccount).toHaveAttribute('href', '/login');
    // And which is which: the primary is the theeeme's fill, the secondary white.
    expect(newHere.style.getPropertyValue('--background-color')).not.toBe('var(--color-white)');
    expect(haveAccount.style.getPropertyValue('--background-color')).toBe('var(--color-white)');
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

/**
 * The end of /welcome (CA, 2026-10-03): one row after the personas, the first
 * button the primary one and the rest secondary. The FAQ used to be a link in
 * the commitment section, "Ideas and bugs" a line under the row, and a signed-in
 * visitor had an "Enter and see how it works" button that took them home.
 */
describe('WelcomePage — the closing row of buttons', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  // The row at the end of the page: the last `.button-row-wide` (the hero has the first).
  const closingRow = (container) => [...container.querySelectorAll('.button-row-wide')].at(-1);
  const linksOf = (row) => [...row.querySelectorAll('a')];
  // The secondary buttons are white (`btnSecondaryStyle`); the primary is the theeeme's fill.
  const isPrimary = (link) =>
    link.style.getPropertyValue('--background-color') !== 'var(--color-white)';

  async function renderSignedOut() {
    apiFetch.mockResolvedValue({ ok: false, status: 401 });
    const view = renderWelcome();
    await screen.findByText(/Welcome to OIUEEI/i);
    return view;
  }

  async function renderSignedIn() {
    localStorage.setItem('userCode', 'USER01');
    apiFetch.mockResolvedValue({ ok: false, status: 401 });
    const view = renderWelcome();
    await screen.findByText(/Welcome to OIUEEI/i);
    return view;
  }

  test('signed out: "New here?" (primary), the FAQ and "Ideas and bugs" (secondary), in that order', async () => {
    const { container } = await renderSignedOut();

    const links = linksOf(closingRow(container));
    expect(links).toHaveLength(3);
    expect(links[0]).toHaveAccessibleName('New here?');
    expect(links[1]).toHaveAccessibleName('Frequently asked questions');
    expect(links[2]).toHaveAccessibleName(/^Ideas and bugs/);
    expect(links.map((a) => a.getAttribute('href'))).toEqual(['/popin', '/faq', FEEDBACK_URL]);
    // The first is the only primary one.
    expect(links.map(isPrimary)).toEqual([true, false, false]);
  });

  test('signed in: the FAQ is the primary button, "Ideas and bugs" the secondary — nothing else', async () => {
    const { container } = await renderSignedIn();

    const links = linksOf(closingRow(container));
    expect(links).toHaveLength(2);
    expect(links[0]).toHaveAccessibleName('Frequently asked questions');
    expect(links[1]).toHaveAccessibleName(/^Ideas and bugs/);
    expect(links.map((a) => a.getAttribute('href'))).toEqual(['/faq', FEEDBACK_URL]);
    expect(links.map(isPrimary)).toEqual([true, false]);
  });

  test.each([
    ['signed out', renderSignedOut],
    ['signed in', renderSignedIn],
  ])('%s: one link to /faq on the whole page, and it says no arrow', async (_who, render) => {
    const { container } = await render();

    const faq = container.querySelectorAll('a[href="/faq"]');
    expect(faq).toHaveLength(1);
    // It is the closing row's button, not a link in the commitment section.
    expect(closingRow(container).contains(faq[0])).toBe(true);
    expect(faq[0]).toHaveTextContent(/^Frequently asked questions$/);
  });

  test.each([
    ['signed out', renderSignedOut],
    ['signed in', renderSignedIn],
  ])('%s: there is no "Enter and see how it works" button any more', async (_who, render) => {
    await render();

    expect(screen.queryByText(/enter and see how it works/i)).toBeNull();
    expect(screen.queryByRole('link', { name: /enter and see/i })).toBeNull();
  });

  test('the hero keeps its own "New here?" and the closing row repeats it in the same words', async () => {
    const { container } = await renderSignedOut();

    const popIn = [...container.querySelectorAll('a[href="/popin"]')];
    expect(popIn).toHaveLength(2);
    expect(popIn.map((a) => a.textContent)).toEqual(['New here?', 'New here?']);
  });
});

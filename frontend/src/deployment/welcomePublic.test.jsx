import { render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { vi, describe, test, expect, beforeEach, afterEach } from 'vitest';

// "Ideas and bugs" of the closing row is this deployment's own Tally form, in the
// language on screen (`externalForms.feedback`, TL1/TLH1, CA 2026-10-05) — English
// here. `FeedbackLink` prefers it to the `VITE_FEEDBACK_URL` this file used to stub to
// have a button at all, so the address expected is the deployment's, read from it.

vi.mock('../services/api', () => ({
  apiFetch: vi.fn(),
  getCsrfToken: () => 'tok',
}));

import { apiFetch } from '../services/api';
import './testI18n';
import WelcomePage from './pages/WelcomePage';
import { nestedTabStops } from '../test/nestedInteractive';
import { externalForms } from './index';

const FEEDBACK_URL = externalForms.feedback.en;

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

  // CA, 2026-10-05: a stranger's hero has no buttons — the title and the wave. The two
  // doors it had ("New here?" primary, "Already have an account?") are the last row of
  // the page now, after the personas (see "the closing row of buttons" below). A
  // member's hero keeps "Create collection" and "Edit profile".
  test('the hero of an anonymous visitor has no buttons, no links and no row of them', async () => {
    apiFetch.mockResolvedValue({ ok: false, status: 401 });

    const { container } = renderWelcome();
    await screen.findByText(/Welcome to OIUEEI/i);

    const hero = container.querySelector('.form-hero');
    // The hero is there: a hero that failed to render would pass the lines below for
    // the wrong reason.
    expect(hero.querySelector('h1')).toHaveTextContent(/Welcome to OIUEEI/i);
    expect(hero.querySelectorAll('a')).toHaveLength(0);
    expect(hero.querySelectorAll('button')).toHaveLength(0);
    expect(hero.querySelector('.button-row-wide')).toBeNull();
    expect(within(hero).queryByText('New here?')).toBeNull();
    expect(within(hero).queryByText('Already have an account?')).toBeNull();
  });

  test('the hero of a signed-in member keeps "Create collection" (primary) and "Edit profile"', async () => {
    localStorage.setItem('userCode', 'USER01');
    apiFetch.mockResolvedValue({ ok: false, status: 401 });

    const { container } = renderWelcome();
    await screen.findByText(/Welcome to OIUEEI/i);

    const links = [...container.querySelectorAll('.form-hero .button-row-wide a')];
    expect(links.map((a) => a.textContent)).toEqual(['Create collection', 'Edit profile']);
    expect(links.map((a) => a.getAttribute('href'))).toEqual(['/collections/new', '/me/edit']);
    expect(
      links.map((a) => a.style.getPropertyValue('--background-color') !== 'var(--color-white)')
    ).toEqual([true, false]);
  });

  // CA, 2026-10-04: the speech-bubble icon left every hero ("too many icons up
  // there") and "Contact us" is the third door of the site footer, on every
  // page. This hero is deployment-only, so core's sweep over the hero corners
  // (`heroCornerLayout.test.jsx`) never reaches it — it imported the deleted
  // component, and the page stopped building, before anyone read what it drew.
  test.each([
    ['an anonymous visitor', null, false],
    ['a signed-in member', 'USER01', true],
  ])('the hero of %s links nothing to /contact', async (_who, userCode, hasDoors) => {
    if (userCode) localStorage.setItem('userCode', userCode);
    apiFetch.mockResolvedValue({ ok: false, status: 401 });

    const { container } = renderWelcome();
    await screen.findByText(/Welcome to OIUEEI/i);

    const hero = container.querySelector('.form-hero');
    // The hero is there, and a member's holds its own doors (a stranger's holds
    // none since 2026-10-05): a hero that failed to render would pass the "no
    // /contact" line below for the wrong reason.
    expect(hero.querySelector('h1')).toHaveTextContent(/Welcome to OIUEEI/i);
    if (hasDoors) expect(hero.querySelectorAll('a').length).toBeGreaterThan(0);
    expect(hero.querySelector('a[href="/contact"]')).toBeNull();
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
 *
 * Since 2026-10-05 (GH1) a stranger's row is "New here?" · the FAQ · "Already have an
 * account?" — the two doors their hero used to have, which now has none — and no "Ideas
 * and bugs"; a member's is as it was: the FAQ (primary) and "Ideas and bugs".
 */
describe('WelcomePage — the closing row of buttons', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  // The row at the end of the page: the last `.button-row-wide` (a member's hero has the first;
  // a stranger's has none, so there it is the only one).
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

  test('signed out: "New here?" (primary), the FAQ and "Already have an account?" (secondary), in that order', async () => {
    const { container } = await renderSignedOut();

    const links = linksOf(closingRow(container));
    expect(links).toHaveLength(3);
    expect(links[0]).toHaveAccessibleName('New here?');
    expect(links[1]).toHaveAccessibleName('Frequently asked questions');
    expect(links[2]).toHaveAccessibleName('Already have an account?');
    expect(links.map((a) => a.getAttribute('href'))).toEqual(['/popin', '/faq', '/login']);
    // The first is the only primary one.
    expect(links.map(isPrimary)).toEqual([true, false, false]);
  });

  test('signed out: no "Ideas and bugs" anywhere on the page, not even as the Tally link', async () => {
    // A stranger is not sent to the feedback form (CA, 2026-10-05): not as a button
    // and not as a link to it.
    const { container } = await renderSignedOut();

    expect(screen.queryByRole('link', { name: /ideas and bugs/i })).toBeNull();
    expect(container.querySelector(`a[href="${FEEDBACK_URL}"]`)).toBeNull();
    expect(container.querySelector('a[href^="https://tally.so"]')).toBeNull();
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

  test('"New here?" is only at the end of the page: one link to /popin, in the closing row', async () => {
    const { container } = await renderSignedOut();

    const popIn = [...container.querySelectorAll('a[href="/popin"]')];
    expect(popIn).toHaveLength(1);
    expect(popIn[0].textContent).toBe('New here?');
    expect(closingRow(container).contains(popIn[0])).toBe(true);
    // …and so is the way back to /login.
    const login = [...container.querySelectorAll('a[href="/login"]')];
    expect(login).toHaveLength(1);
    expect(closingRow(container).contains(login[0])).toBe(true);
  });
});

import { render, screen, waitFor } from '@testing-library/react';
import { vi, describe, test, expect, beforeEach } from 'vitest';

import './testI18n';
import App from '../App';
import { deploymentRoutes, popInPath, aboutPath, faqPath } from './index';

/**
 * The pages this deployment adds, mounted and reachable.
 *
 * `src/test/deployment.test.jsx` (upstream) pins the *mechanism* with the module
 * mocked: a route above the catch-all, a button that follows popInPath. This
 * pins the *contents* — that this deployment really does declare /popin,
 * /welcome and /faq, and that App.jsx renders them from the real module.
 *
 * It matters because the failure is silent in both directions. Replace this
 * directory badly and the deployment simply stops answering two URLs that are
 * in emails, in printed QR codes and in the site footer; nothing errors, the
 * 404 page just starts appearing where a page used to be.
 */

window.scrollTo = vi.fn();
globalThis.fetch = vi.fn(() =>
  Promise.resolve({ ok: false, status: 400, json: () => Promise.resolve({}) })
);

beforeEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
});

describe('this deployment declares its own pages', () => {
  test('every route, and the paths the shared components read', () => {
    expect(deploymentRoutes.map((route) => route.path)).toEqual(['/popin', '/welcome', '/faq']);
    // The three values that make LoginPage, SiteFooter, CollectionPage and
    // VerifyPage behave as a hosted service rather than as an invite-only
    // checkout, without any of them being edited. Each must name a route
    // declared above: upstream's rule is that a null means no link at all,
    // precisely so that no link ever points at a page that is not there.
    // The "new here?" button on /login goes to the page that says what this is,
    // not straight to the open door: /welcome offers the door in its hero.
    expect(popInPath).toBe('/welcome');
    expect(aboutPath).toBe('/welcome');
    expect(faqPath).toBe('/faq');

    const declared = deploymentRoutes.map((route) => route.path);
    for (const path of [popInPath, aboutPath, faqPath]) {
      if (path !== null) expect(declared).toContain(path);
    }
  });
});

describe('the app serves them', () => {
  test('/popin renders the open door rather than the 404 page', async () => {
    window.history.pushState({}, '', '/popin');
    render(<App />);

    expect(await screen.findByRole('heading', { name: /come meet us/i })).toBeInTheDocument();
  });

  test('/popin has no link to /login: "Already have an account?" is offered on /welcome', async () => {
    // The whole page, not the mocked component: what the visitor sees is
    // MagicLinkJoinPage honouring the prop PopInPage passes it.
    window.history.pushState({}, '', '/popin');
    render(<App />);
    await screen.findByRole('heading', { name: /come meet us/i });

    expect(document.querySelector('a[href="/login"]')).toBeNull();
    expect(screen.queryByText(/already have an account/i)).toBeNull();
  });

  test('/welcome renders the page that says what this is', async () => {
    window.history.pushState({}, '', '/welcome');
    render(<App />);

    await waitFor(() => expect(document.title).toMatch(/welcome/i));
    expect(document.querySelector('a[href="/popin"]')).not.toBeNull();
  });

  test('/welcome links /legal exactly once, from the site footer', async () => {
    // The page used to repeat the footer's "Legal notice & privacy" link in the
    // commitment section (CA took it out, 2026-10-03). Rendered whole — App, so
    // the footer is there — because the page alone cannot say how many a
    // visitor sees.
    window.history.pushState({}, '', '/welcome');
    render(<App />);
    await screen.findByRole('heading', { level: 1, name: /Welcome to OIUEEI/i });

    const links = document.querySelectorAll('a[href="/legal"]');
    expect(links).toHaveLength(1);
    expect(links[0].closest('footer')).not.toBeNull();
  });

  test.each([
    ['signed out', null],
    ['signed in', 'USER01'],
  ])(
    '/welcome, %s: one link to /faq on the whole page, and no "Enter" button',
    async (_who, userCode) => {
      // The FAQ moved from a link in the commitment section to a button in the
      // closing row (CA, 2026-10-03); rendered whole, so a stray second link
      // anywhere in the App — hero, footer, a leftover — would be counted.
      if (userCode) localStorage.setItem('userCode', userCode);
      window.history.pushState({}, '', '/welcome');
      render(<App />);
      await screen.findByRole('heading', { level: 1, name: /Welcome to OIUEEI/i });

      expect(document.querySelectorAll('a[href="/faq"]')).toHaveLength(1);
      expect(screen.queryByText(/enter and see how it works/i)).toBeNull();
    }
  );

  test('/login\'s "new here?" button leads to /welcome, not straight to /popin', async () => {
    // CA, 2026-10-03: someone new reads what this is before being asked for an
    // email. The path is the deployment's `popInPath`, which LoginPage reads
    // without being edited — so this is what pins it end to end, in the page.
    window.history.pushState({}, '', '/login');
    render(<App />);

    const button = await screen.findByRole('link', { name: /new here/i });
    expect(button).toHaveAttribute('href', '/welcome');
    expect(document.querySelector('a[href="/popin"]')).toBeNull();
  });

  test('/login carries the claim only this deployment may make', async () => {
    window.history.pushState({}, '', '/login');
    render(<App />);

    // `login.operator` is empty upstream on purpose — a self-hoster cannot
    // inherit a statement about somebody else's servers — and LoginPage renders
    // the paragraph only when it is non-empty. So losing this string in a merge
    // does not break anything: the sentence simply stops being on the page.
    expect(await screen.findByText(/European servers/i)).toBeInTheDocument();
  });

  test('the footer reaches the about page from anywhere', async () => {
    window.history.pushState({}, '', '/login');
    render(<App />);

    // Upstream this link is absent (there is no such page); here it is the
    // stranger's way in from every page in the app.
    await waitFor(() => expect(document.querySelector('a[href="/welcome"]')).not.toBeNull());
  });
});

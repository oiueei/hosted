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
    expect(popInPath).toBe('/popin');
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

  test('/welcome renders the page that says what this is', async () => {
    window.history.pushState({}, '', '/welcome');
    render(<App />);

    await waitFor(() => expect(document.title).toMatch(/welcome/i));
    expect(document.querySelector('a[href="/popin"]')).not.toBeNull();
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

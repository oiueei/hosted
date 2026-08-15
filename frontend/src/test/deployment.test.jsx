import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { vi, describe, test, expect, beforeEach, afterEach } from 'vitest';

/**
 * `frontend/src/deployment/` — the directory a deployment replaces instead of
 * editing App.jsx, LoginPage.jsx and the locale files.
 *
 * Two halves are worth protecting. **Upstream adds nothing**: an OIUEEI
 * checkout must render exactly the app it rendered before this indirection
 * existed. And **a replacement actually takes effect** — a route that mounts
 * where it can still be reached, a button that follows the path it is given or
 * disappears when there is none.
 *
 * The mocked-module tests are the only way to exercise the second half from
 * this repository, since upstream's values are by definition the empty ones.
 */

// jsdom has no scrollTo (RouteFocusReset calls it) and App's mount effect hits
// the network — keep both inert.
window.scrollTo = vi.fn();
globalThis.fetch = vi.fn(() =>
  Promise.resolve({ ok: false, status: 400, json: () => Promise.resolve({}) })
);

beforeEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
  vi.resetModules();
});

afterEach(() => {
  vi.doUnmock('../deployment');
  window.history.pushState({}, '', '/');
});

describe('the module keeps its contract', () => {
  test('exports the four values App.jsx and the pages read', async () => {
    /* Asserted as a **shape**, not as this checkout's values.

       The obvious version of this test — `deploymentRoutes` is `[]`, both paths
       are null — is true upstream and false by design in any deployment that
       replaces the directory, which is what the directory is *for*. A test that
       fails on the branch it was built to serve is one that branch has to edit,
       and editing it is a merge conflict on every release: exactly the cost
       this whole indirection exists to avoid.

       What matters on both sides is that the four exports still have the shapes
       App.jsx, LoginPage, SiteFooter, CollectionPage and VerifyPage read. The
       behaviours themselves are pinned below with the module mocked, which
       works identically wherever it runs. */
    const { deploymentRoutes, deploymentI18n, popInPath, aboutPath } = await import(
      '../deployment'
    );

    expect(Array.isArray(deploymentRoutes)).toBe(true);
    deploymentRoutes.forEach((route) => {
      expect(typeof route.path).toBe('string');
      expect(route.Component).toBeTruthy();
    });
    expect(typeof deploymentI18n).toBe('object');
    expect(deploymentI18n).not.toBeNull();
    [popInPath, aboutPath].forEach((path) => {
      expect(path === null || typeof path === 'string').toBe(true);
    });
  });
});

describe('a deployment that adds a route', () => {
  test('mounts it where the catch-all cannot swallow it', async () => {
    // The failure this guards is silent: a route declared after `path="*"`
    // renders the 404 page, and nothing about the app looks broken — it just
    // insists the deployment's own page does not exist.
    vi.doMock('../deployment', () => ({
      deploymentRoutes: [
        { path: '/request-access', Component: () => <p>Ask to join</p> },
      ],
      popInPath: null,
      aboutPath: null,
      deploymentI18n: {},
    }));
    const { default: App } = await import('../App');

    window.history.pushState({}, '', '/request-access');
    render(<App />);

    expect(await screen.findByText('Ask to join')).toBeInTheDocument();
  });

  test('unknown paths still reach the 404 page', async () => {
    /* The catch-all must survive the insertion above it. */
    vi.doMock('../deployment', () => ({
      deploymentRoutes: [
        { path: '/request-access', Component: () => <p>Ask to join</p> },
      ],
      popInPath: null,
      aboutPath: null,
      deploymentI18n: {},
    }));
    const { default: App } = await import('../App');

    // Two segments on purpose: a single-segment path matches `/:userCode`, the
    // profile route, and would be answered by RequireAuth's redirect to /login
    // rather than by the catch-all this test is about.
    window.history.pushState({}, '', '/no-such/page');
    render(<App />);

    // Asserted on the title NotFoundPage sets, rather than its visible copy:
    // this file re-imports the module graph per test, so the i18n instance
    // React sees is not the one the shared test setup primed, and the rendered
    // strings can be raw keys. Either way the title names the page that
    // mounted, which is the fact under test.
    await waitFor(() => expect(document.title).toMatch(/not.?found/i));
    expect(screen.queryByText('Ask to join')).not.toBeInTheDocument();
  });
});

describe('the open-door button follows popInPath', () => {
  test('is not rendered at all when the deployment has no open door', async () => {
    vi.doMock('../deployment', () => ({
      deploymentRoutes: [],
      popInPath: null,
      aboutPath: null,
      deploymentI18n: {},
    }));
    const { default: LoginPage } = await import('../pages/LoginPage');

    render(<MemoryRouter><LoginPage /></MemoryRouter>);

    // Nothing dangling: no button, and no link pointing at the page that is
    // not there. Sending a stranger to a 404 is worse than telling them the
    // truth, which is that they get in by invitation.
    expect(screen.queryByRole('link', { name: /pop in|new here/i })).not.toBeInTheDocument();
    expect(document.querySelector('a[href="/popin"]')).toBeNull();
  });

  test('points wherever the deployment says, not at a hard-coded path', async () => {
    vi.doMock('../deployment', () => ({
      deploymentRoutes: [],
      popInPath: '/join-us',
      aboutPath: null,
      deploymentI18n: {},
    }));
    const { default: LoginPage } = await import('../pages/LoginPage');

    render(<MemoryRouter><LoginPage /></MemoryRouter>);

    await waitFor(() => {
      expect(document.querySelector('a[href="/join-us"]')).not.toBeNull();
    });
  });
});

describe('the about link follows aboutPath', () => {
  test('the footer links it when the deployment has such a page', async () => {
    vi.doMock('../deployment', () => ({
      deploymentRoutes: [],
      popInPath: null,
      aboutPath: '/about-us',
      deploymentI18n: {},
    }));
    const { default: SiteFooter } = await import('../components/SiteFooter');

    render(<MemoryRouter><SiteFooter /></MemoryRouter>);

    // Upstream this link is absent entirely (siteFooter.test.jsx pins that).
    // Here it exists and points where the deployment put its page — not at a
    // path this repository hard-codes.
    expect(document.querySelector('a[href="/about-us"]')).not.toBeNull();
    expect(document.querySelector('a[href="/legal"]')).not.toBeNull();
  });
});

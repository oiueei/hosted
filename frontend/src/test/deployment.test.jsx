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

describe('the standalone adds nothing', () => {
  test('no extra routes and no extra copy', async () => {
    const { deploymentRoutes, deploymentI18n } = await import('../deployment');

    expect(deploymentRoutes).toEqual([]);
    expect(deploymentI18n).toEqual({});
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
      deploymentI18n: {},
    }));
    const { default: LoginPage } = await import('../pages/LoginPage');

    render(<MemoryRouter><LoginPage /></MemoryRouter>);

    await waitFor(() => {
      expect(document.querySelector('a[href="/join-us"]')).not.toBeNull();
    });
  });

  test('welcome sends a signed-out visitor to /login when there is no open door', async () => {
    vi.doMock('../deployment', () => ({
      deploymentRoutes: [],
      popInPath: null,
      deploymentI18n: {},
    }));
    const { default: WelcomePage } = await import('../pages/WelcomePage');

    render(<MemoryRouter><WelcomePage /></MemoryRouter>);

    // /welcome is the page a stranger is handed. Its call to action must lead
    // to the door that does exist rather than nowhere.
    await waitFor(() => {
      expect(document.querySelector('a[href="/login"]')).not.toBeNull();
    });
    expect(document.querySelector('a[href="/popin"]')).toBeNull();
  });
});

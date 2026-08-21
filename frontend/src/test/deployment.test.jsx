import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route, useLocation } from 'react-router';
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
  vi.doUnmock('../services/api');
  window.history.pushState({}, '', '/');
});

describe('the module keeps its contract', () => {
  test('exports the five values App.jsx and the pages read', async () => {
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
    const { deploymentRoutes, deploymentI18n, popInPath, aboutPath, faqPath } = await import(
      '../deployment'
    );

    expect(Array.isArray(deploymentRoutes)).toBe(true);
    deploymentRoutes.forEach((route) => {
      expect(typeof route.path).toBe('string');
      expect(route.Component).toBeTruthy();
    });
    expect(typeof deploymentI18n).toBe('object');
    expect(deploymentI18n).not.toBeNull();
    [popInPath, aboutPath, faqPath].forEach((path) => {
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
      faqPath: null,
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
      faqPath: null,
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
      faqPath: null,
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
      faqPath: null,
      deploymentI18n: {},
    }));
    const { default: LoginPage } = await import('../pages/LoginPage');

    render(<MemoryRouter><LoginPage /></MemoryRouter>);

    await waitFor(() => {
      expect(document.querySelector('a[href="/join-us"]')).not.toBeNull();
    });
  });
});

describe('the faq link follows faqPath', () => {
  test('is not rendered at all when the deployment has no help page', async () => {
    vi.doMock('../deployment', () => ({
      deploymentRoutes: [],
      popInPath: null,
      aboutPath: null,
      faqPath: null,
      deploymentI18n: {},
    }));
    const { default: LoginPage } = await import('../pages/LoginPage');

    render(<MemoryRouter><LoginPage /></MemoryRouter>);

    // Same reasoning as the pop-in button: a link to a 404 is worse than one
    // link fewer, so upstream — with no FAQ content of its own — offers none.
    expect(screen.queryByRole('link', { name: /questions|faq/i })).not.toBeInTheDocument();
    expect(document.querySelector('a[href="/faq"]')).toBeNull();
  });

  test('points wherever the deployment says, not at a hard-coded path', async () => {
    vi.doMock('../deployment', () => ({
      deploymentRoutes: [],
      popInPath: null,
      aboutPath: null,
      faqPath: '/help',
      deploymentI18n: {},
    }));
    const { default: LoginPage } = await import('../pages/LoginPage');

    render(<MemoryRouter><LoginPage /></MemoryRouter>);

    await waitFor(() => {
      expect(document.querySelector('a[href="/help"]')).not.toBeNull();
    });
  });
});

describe('the about link follows aboutPath', () => {
  test('the footer links it when the deployment has such a page', async () => {
    vi.doMock('../deployment', () => ({
      deploymentRoutes: [],
      popInPath: null,
      aboutPath: '/about-us',
      faqPath: null,
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

describe("the dashboard's second button follows aboutPath", () => {
  /* The first screen a brand-new account sees: no collections yet, so the empty
     state offers "create your first" and — where there is something to read —
     "learn how".

     This is the one site the /welcome sweep missed. The route left with the
     demo, the footer got a test pinning its absence, and this button kept a
     hard-coded `to="/welcome"` that quietly resolved to the 404 page, on the
     screen least able to afford it. Hence a guard on both halves. */
  const ok = (body) =>
    Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });

  function mockEmptyDashboard() {
    vi.doMock('../services/api', () => ({
      apiFetch: vi.fn((url) => {
        if (url.startsWith('/api/v1/auth/me/')) {
          return ok({ code: 'ABC123', name: 'Ada', koro: 'basic' });
        }
        // An account that owns nothing yet — the empty state under test.
        // Note the two shapes: /collections/ is paginated (`.results`) while
        // /invited-collections/ and /my-invitations/ answer a bare array, and
        // HomePage reads each accordingly.
        if (url.startsWith('/api/v1/collections/')) return ok({ results: [] });
        return ok([]);
      }),
      getCsrfToken: vi.fn(() => 'mock-csrf'),
      extractApiError: vi.fn(() => ''),
    }));
  }

  const renderHome = async () => {
    const { default: HomePage } = await import('../pages/HomePage');
    localStorage.setItem('userCode', 'ABC123');
    render(
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>
    );
  };

  test('no about page, no button — and nothing pointing at the route that left', async () => {
    vi.doMock('../deployment', () => ({
      deploymentRoutes: [],
      popInPath: null,
      aboutPath: null,
      faqPath: null,
      deploymentI18n: {},
    }));
    mockEmptyDashboard();
    await renderHome();

    // The empty state has rendered: it is the "create your first" button that
    // proves we are looking at it and not at a loading or error branch.
    await waitFor(() =>
      expect(document.querySelector('a[href="/collections/new"]')).not.toBeNull()
    );
    expect(document.querySelector('a[href="/welcome"]')).toBeNull();
    // Scoped to the empty state by its own copy: HomePage has a second
    // `.button-row-wide` up in the hero, and a document-wide selector would be
    // asserting about that one too. Exactly one link here, and it is the only
    // one this screen can honestly offer — no dangling second button however
    // the href had been spelled.
    const emptyState = screen.getByText('You have no active collections yet.').parentElement;
    const links = [...emptyState.querySelectorAll('a')];
    expect(links.map((a) => a.getAttribute('href'))).toEqual(['/collections/new']);
    expect(screen.queryByText('See how it works')).not.toBeInTheDocument();
  });

  test('points wherever the deployment put its page', async () => {
    vi.doMock('../deployment', () => ({
      deploymentRoutes: [],
      popInPath: null,
      aboutPath: '/about-us',
      faqPath: null,
      deploymentI18n: {},
    }));
    mockEmptyDashboard();
    await renderHome();

    await waitFor(() =>
      expect(document.querySelector('a[href="/about-us"]')).not.toBeNull()
    );
  });
});

describe('a "welcome" landing follows aboutPath', () => {
  /* The backend answers `landing: "welcome"` only for a deployment with an open
     door of its own — nothing upstream produces it, and verifyPage.test.jsx
     pins what a checkout without such a page does with it (goes home rather
     than to a 404). This is the other side: where the page exists, the brand-new
     visitor's very first click after signing in has to reach it. */
  function Landing() {
    const { pathname } = useLocation();
    return <p>{`landed on ${pathname}`}</p>;
  }

  async function renderVerifyAt(aboutPath) {
    vi.doMock('../deployment', () => ({
      deploymentRoutes: [],
      popInPath: null,
      aboutPath,
      faqPath: null,
      deploymentI18n: {},
    }));
    globalThis.fetch = vi.fn(() =>
      Promise.resolve({
        ok: true,
        status: 200,
        json: () =>
          Promise.resolve({
            action: 'MAGIC_LINK',
            landing: 'welcome',
            user: { code: 'USR001', name: 'Lala', email: 'lala@test.com' },
          }),
      })
    );
    const { default: VerifyPage } = await import('../pages/VerifyPage');

    render(
      <MemoryRouter initialEntries={['/verify/TOKEN123']}>
        <Routes>
          <Route path="/verify/:code" element={<VerifyPage />} />
          <Route path="*" element={<Landing />} />
        </Routes>
      </MemoryRouter>
    );
  }

  test('lands on the deployment’s own page when it has one', async () => {
    await renderVerifyAt('/about-us');

    expect(await screen.findByText('landed on /about-us')).toBeInTheDocument();
  });

  test('falls through to home when it has none', async () => {
    // The upstream shape, asserted through the same mock so the two answers sit
    // side by side: null is a value the field is allowed to hold, not an
    // oversight, and it must never navigate to a page that isn't there.
    await renderVerifyAt(null);

    expect(await screen.findByText('landed on /')).toBeInTheDocument();
  });
});

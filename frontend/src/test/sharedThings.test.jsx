import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { axe, toHaveNoViolations } from 'jest-axe';
import { vi, describe, test, expect, beforeEach } from 'vitest';

expect.extend(toHaveNoViolations);

window.scrollTo = vi.fn();

vi.mock('../services/api', () => ({
  apiFetch: vi.fn(),
  getCsrfToken: vi.fn(() => 'mock-csrf'),
}));

import { apiFetch } from '../services/api';
import SharedThingsPage from '../pages/SharedThingsPage';

const ok = (body) => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });

/** One page per call, in order — the pager's own sequence. */
const mockPages = (...pages) => {
  pages.forEach((page) => apiFetch.mockImplementationOnce(() => ok(page)));
};

const THING = {
  code: 'THG001',
  headline: 'A cordless drill',
  description: '18V, two batteries',
  type: 'LEND_THING',
  status: 'ACTIVE',
  owner: 'OWN001',
  owner_name: 'Lili',
  created: '2026-08-01T10:00:00Z',
  thumbnail_url: '',
  gallery_urls: [],
  tags: [],
  collection_code: 'COL001',
  collection_headline: "Lili's Lending Library",
  collection_owner: 'OWN001',
};

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem('userCode', 'ME0001');
  // `resetAllMocks`, not `clearAllMocks`: clearing wipes the recorded calls but
  // leaves the `mockImplementationOnce` queue intact, so a page a test queued
  // and never consumed is still sitting there when the next test runs. Every
  // test in this file queues responses that way, so the leak made results
  // order-dependent — the axe scans below passed in a full-file run and failed
  // when run alone, which is the wrong way round for a test to be believed.
  vi.resetAllMocks();
});

const renderPage = () =>
  render(
    <MemoryRouter>
      <SharedThingsPage />
    </MemoryRouter>
  );

/**
 * The cross-group view a member never had.
 *
 * `/api/v1/invited-things/` shipped documented and uncalled, so somebody in five
 * groups could only see what was in them by opening each one. The page's job is
 * to answer "what is being shared with me?" in one screen.
 */
describe('SharedThingsPage', () => {
  test('lists things from the groups you belong to, and links each to its collection', async () => {
    apiFetch.mockImplementation((url) =>
      url.startsWith('/api/v1/invited-things/') ? ok({ results: [THING], next: null }) : ok({})
    );

    renderPage();

    expect(await screen.findByText('A cordless drill')).toBeInTheDocument();
    expect(apiFetch).toHaveBeenCalledWith('/api/v1/invited-things/', expect.anything());
    // The card knows which collection it came from, so its links stay in context.
    expect(screen.getByRole('link', { name: /A cordless drill/ })).toHaveAttribute(
      'href',
      '/collections/COL001/things/THG001'
    );
  });

  test('an empty result says so and offers the way back, not a blank page', async () => {
    apiFetch.mockImplementation(() => ok({ results: [], next: null }));

    renderPage();

    expect(
      await screen.findByText(/nothing has been shared in your groups yet/i)
    ).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /back to my groups/i })).toHaveAttribute('href', '/');
  });

  test('a failed load shows a persistent error, not an endless spinner', async () => {
    apiFetch.mockImplementation(() =>
      Promise.resolve({ ok: false, status: 500, json: () => Promise.resolve({}) })
    );

    renderPage();

    expect(await screen.findByText(/couldn't load what's been shared/i)).toBeInTheDocument();
  });

  test('a second page is offered only when the API says there is one', async () => {
    apiFetch.mockImplementation((url) =>
      url.startsWith('/api/v1/invited-things/')
        ? ok({ results: [THING], next: 'http://testserver/api/v1/invited-things/?page=2' })
        : ok({})
    );

    renderPage();

    await screen.findByText('A cordless drill');
    expect(screen.getByRole('button', { name: /load more/i })).toBeInTheDocument();
  });

  test('no "Load more" when the first page is the only page', async () => {
    mockPages({ results: [THING], next: null });

    renderPage();

    await screen.findByText('A cordless drill');
    expect(screen.queryByRole('button', { name: /load more/i })).toBeNull();
  });
});

/**
 * The pager itself. Until now only its *button* was tested — that it appeared
 * when the API said there was a second page. Everything the button does was
 * unexecuted: the append, the origin strip, and standing down when exhausted.
 * Both sibling pagers (`MyBookingsPage`, `OwnerBookingsPage`) carry exactly
 * these, and this page is the one that shipped without them.
 */
describe('SharedThingsPage pagination', () => {
  test('"Load more" appends the next page and keeps the request same-origin', async () => {
    mockPages(
      { results: [THING], next: 'http://testserver/api/v1/invited-things/?page=2' },
      { results: [{ ...THING, code: 'THG002', headline: 'A folding ladder' }], next: null }
    );
    renderPage();
    await screen.findByText('A cordless drill');

    fireEvent.click(screen.getByRole('button', { name: /load more/i }));

    expect(await screen.findByText('A folding ladder')).toBeInTheDocument();
    // The first page stays: the pager appends, it doesn't replace.
    expect(screen.getByText('A cordless drill')).toBeInTheDocument();
    // DRF hands back an absolute URL. Sending it verbatim would leave the Vite
    // proxy in dev and go cross-origin everywhere — which drops the auth
    // cookies, so the second page would come back empty or 401.
    expect(apiFetch.mock.calls[1][0]).toBe('/api/v1/invited-things/?page=2');
    // Exhausted, the pager stands down rather than re-fetching the same page.
    await waitFor(() => expect(screen.queryByRole('button', { name: /load more/i })).toBeNull());
  });

  test('a dropped connection while paging says so instead of failing silently', async () => {
    mockPages({ results: [THING], next: 'http://testserver/api/v1/invited-things/?page=2' });
    apiFetch.mockImplementationOnce(() => Promise.reject(new TypeError('Failed to fetch')));
    renderPage();
    await screen.findByText('A cordless drill');

    fireEvent.click(screen.getByRole('button', { name: /load more/i }));

    expect(await screen.findByText(/connection/i)).toBeInTheDocument();
    // Reported without costing the reader the page they were already looking at.
    expect(screen.getByText('A cordless drill')).toBeInTheDocument();
  });

  test('a refused second page says so and keeps the first one on screen', async () => {
    // Regression: `!res.ok` had no branch at all here. The button re-enabled,
    // nothing appeared and nothing said why — a control that visibly does
    // nothing, which reads as a broken app rather than a failed request.
    mockPages({ results: [THING], next: 'http://testserver/api/v1/invited-things/?page=2' });
    apiFetch.mockImplementationOnce(() =>
      Promise.resolve({ ok: false, status: 500, json: () => Promise.resolve({}) })
    );
    renderPage();
    await screen.findByText('A cordless drill');

    fireEvent.click(screen.getByRole('button', { name: /load more/i }));

    expect(await screen.findByText(/couldn't load more/i)).toBeInTheDocument();
    // And the failure must not swap the whole page for the error screen: the
    // first page is still there, and so is the way to retry.
    expect(screen.getByText('A cordless drill')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /load more/i })).toBeEnabled();
  });
});

/**
 * The axe sweep in `smoke.test.jsx` covers all 30 other routes; this page was
 * the one it never reached, so its markup shipped unscanned. Scanned here
 * rather than added to that sweep because the fixtures live in this file — and
 * because the generic helper can only ever reach a page's default state, while
 * the three states below are what a member actually lands on. DESIGN §5 puts
 * WCAG 2.1 AA at the floor, not the ceiling.
 */
describe('SharedThingsPage — accessibility', () => {
  /**
   * Pinned with `getByRole` rather than left to the axe scan below. axe's
   * `heading-order` verdict turned out not to be reproducible in this suite:
   * with a byte-identical DOM it reported the h1→h3 skip when these three tests
   * ran alone and stayed silent when the whole file ran, because axe-core keeps
   * state between `axe.run` calls in one process. A guard that only fires
   * depending on what ran before it is not a guard, so the outline is asserted
   * directly here — the scan below still earns its place for the label, role and
   * name rules, which did reproduce.
   */
  test('the card headings continue the page outline instead of skipping a level', async () => {
    mockPages({ results: [THING], next: null });
    renderPage();
    await screen.findByText('A cordless drill');

    expect(screen.getByRole('heading', { level: 1, name: /shared/i })).toBeInTheDocument();
    // The grid hangs straight off the page h1 with no section heading between
    // them, so a card is level 2 here — level 3 (the default, which is right on
    // CollectionPage, where an h2 does sit in between) would skip a level and
    // tell a screen reader walking the outline that a heading is missing.
    expect(screen.getByRole('heading', { level: 2, name: 'A cordless drill' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { level: 3 })).not.toBeInTheDocument();
  });

  test('the populated grid has no axe violations', async () => {
    mockPages({ results: [THING, { ...THING, code: 'THG002', headline: 'A ladder' }], next: null });
    const { container } = renderPage();
    await screen.findByText('A cordless drill');

    expect(await axe(container)).toHaveNoViolations();
  });

  test('the empty state has no axe violations', async () => {
    mockPages({ results: [], next: null });
    const { container } = renderPage();
    await screen.findByText(/nothing/i);

    expect(await axe(container)).toHaveNoViolations();
  });

  test('the error state has no axe violations', async () => {
    apiFetch.mockImplementationOnce(() =>
      Promise.resolve({ ok: false, status: 500, json: () => Promise.resolve({}) })
    );
    const { container } = renderPage();
    await screen.findByRole('heading', { level: 1 });

    // The error screen swaps the whole page out, so it is a distinct render
    // tree from the two above — an unlabelled Notification here would never be
    // caught by scanning the populated grid.
    expect(await axe(container)).toHaveNoViolations();
  });
});

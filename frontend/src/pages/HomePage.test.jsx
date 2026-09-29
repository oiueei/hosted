import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { vi, describe, test, expect, beforeEach } from 'vitest';

window.scrollTo = vi.fn();

vi.mock('../services/api', () => ({
  apiFetch: vi.fn(),
  getCsrfToken: vi.fn(() => 'mock-csrf'),
}));

import { apiFetch } from '../services/api';
import HomePage from './HomePage';

const USER = { code: 'USR001', name: 'Lulu', email: 'lulu@example.com', koro: 'basic' };
const GROUP = {
  code: 'COL009',
  headline: 'Bibliocoses',
  status: 'ACTIVE',
  things: [],
  invites: [],
};
const MINE = { ...GROUP, code: 'COL001', headline: 'My workshop' };

const ok = (body) => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });

// What the API answers each of the dashboard's five reads.
function dashboardRoutes({ mine = [], invited = [], invitations = [], user = USER }) {
  return (url) => {
    if (url.startsWith('/api/v1/auth/me/')) return ok(user);
    if (url.startsWith('/api/v1/collections/')) return ok({ results: mine });
    if (url.startsWith('/api/v1/invited-collections/')) return ok(invited);
    if (url.startsWith('/api/v1/my-invitations/')) return ok(invitations);
    return ok([]); // the inbox
  };
}

function mockDashboard(options = {}) {
  apiFetch.mockImplementation(dashboardRoutes(options));
}

// A real connection failure rejects with a TypeError; an HTTP error status does not.
const dropped = () => Promise.reject(new TypeError('Failed to fetch'));
const refused = () => Promise.resolve({ ok: false, status: 500, json: () => Promise.resolve({}) });

const renderHome = () =>
  render(
    <MemoryRouter>
      <HomePage />
    </MemoryRouter>
  );

const sectionOrder = () =>
  screen
    .getAllByRole('heading', { level: 2 })
    .map((h) => h.textContent)
    .filter((text) => text === 'My collections' || text === 'Shared with me');

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem('userCode', 'USR001');
  vi.clearAllMocks();
});

/**
 * Most accounts are members: they arrive through somebody else's group and may
 * never start one. Home used to lead with "My collections" for everyone — an
 * empty state and "Create your first collection" above the one thing a member
 * has, which on a phone sat below the fold under the hero's buttons.
 */
describe('HomePage — which section leads', () => {
  test('a member who owns nothing sees their groups first, the invitation to create after', async () => {
    mockDashboard({ mine: [], invited: [GROUP] });
    renderHome();

    await screen.findByText('Bibliocoses');
    expect(sectionOrder()).toEqual(['Shared with me', 'My collections']);
    // Still offered — just not first.
    expect(screen.getByRole('link', { name: 'Create your first collection' })).toBeInTheDocument();
  });

  test('someone who runs a collection keeps it first', async () => {
    mockDashboard({ mine: [MINE], invited: [GROUP] });
    renderHome();

    await screen.findByText('My workshop');
    expect(sectionOrder()).toEqual(['My collections', 'Shared with me']);
  });

  test('a brand-new account with no groups yet is still pointed at creating one first', async () => {
    mockDashboard({ mine: [], invited: [] });
    renderHome();

    await screen.findByText('No one has shared a collection with you yet.');
    expect(sectionOrder()).toEqual(['My collections', 'Shared with me']);
  });
});

/**
 * The hero used to repeat the account menu: "My profile", "My requests" and, for
 * some accounts, "Requests to me", each a full-width button, so a phone showed up
 * to four of them stacked before the inbox and the groups. It keeps the one thing
 * only Home offers; the rest is in the account menu, in every hero.
 */
describe('HomePage — the hero holds one button', () => {
  // The accounts the old row judged differently: a plain member, someone who owns
  // a thing (a Community contribution), a curator of a Proprietary collection.
  const ACCOUNTS = [
    ['a member', { invited: [GROUP] }],
    ['someone who owns a thing', { user: { ...USER, things: [{ code: 'THG001' }] } }],
    [
      'a curator of a Proprietary collection',
      { mine: [{ ...MINE, mode: 'PROPRIETARY', is_curator: true }] },
    ],
  ];

  test.each(ACCOUNTS)('%s sees only "Create collection" in the hero', async (_who, options) => {
    mockDashboard(options);
    const { container } = renderHome();
    await screen.findByText(/Lulu/);

    const row = container.querySelector('.form-hero .button-row-wide');
    const links = [...row.querySelectorAll('a')];
    expect(links.map((a) => [a.textContent, a.getAttribute('href')])).toEqual([
      ['Create collection', '/collections/new'],
    ]);
    expect(row.querySelectorAll('button')).toHaveLength(0);
    // …and nothing else in the hero points at the account's own pages.
    const hero = container.querySelector('.form-hero');
    for (const href of ['/me', '/my-bookings', '/owner-bookings']) {
      expect(hero.querySelector(`a[href="${href}"]`)).toBeNull();
    }
  });

  test('the account menu still reaches My profile, My requests and Requests to me', async () => {
    mockDashboard({ invited: [GROUP] });
    renderHome();
    await screen.findByText(/Lulu/);

    fireEvent.click(screen.getByRole('button', { name: 'Your account' }));

    const menu = screen.getByRole('navigation', { name: 'Your account' });
    expect(within(menu).getByRole('link', { name: 'My profile' })).toHaveAttribute('href', '/me');
    expect(within(menu).getByRole('link', { name: 'My requests' })).toHaveAttribute(
      'href',
      '/my-bookings'
    );
    expect(within(menu).getByRole('link', { name: 'Requests to me' })).toHaveAttribute(
      'href',
      '/owner-bookings'
    );
  });
});

/**
 * The dashboard is five reads, and each can fail in its own way. A dropped
 * connection (a rejected fetch) is not the same as a server that answered with
 * an error, and both must be said, with a way to try again — otherwise the page
 * is an endless spinner or a silent gap.
 */
describe('HomePage — when the connection drops', () => {
  test('a dropped connection is said plainly, and Retry brings the dashboard back', async () => {
    apiFetch.mockImplementation(dropped);
    renderHome();

    expect(await screen.findByText('Connection problem')).toBeInTheDocument();
    expect(screen.getByText(/We can't reach OIUEEI right now/)).toBeInTheDocument();
    expect(screen.queryByText('My workshop')).not.toBeInTheDocument();

    mockDashboard({ mine: [MINE] });
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));

    expect(await screen.findByText('My workshop')).toBeInTheDocument();
    // The warning goes with the failure it reported.
    expect(screen.queryByText('Connection problem')).not.toBeInTheDocument();
  });

  test('the browser getting its connection back reloads the dashboard without a click', async () => {
    apiFetch.mockImplementation(dropped);
    renderHome();
    await screen.findByText('Connection problem');

    mockDashboard({ mine: [MINE] });
    fireEvent(window, new Event('online'));

    expect(await screen.findByText('My workshop')).toBeInTheDocument();
    expect(screen.queryByText('Connection problem')).not.toBeInTheDocument();
  });

  test('the inbox losing its connection warns on the dashboard too', async () => {
    const routes = dashboardRoutes({ mine: [MINE] });
    apiFetch.mockImplementation((url) =>
      url.startsWith('/api/v1/inbox/') ? dropped() : routes(url)
    );
    renderHome();

    // The rest of the page loaded; the banner sits above it, the page stays.
    expect(await screen.findByText('My workshop')).toBeInTheDocument();
    expect(await screen.findByText('Connection problem')).toBeInTheDocument();
  });
});

describe('HomePage — a section the server refuses', () => {
  test('it says so inline, leaves the other section alone, and Retry brings it back', async () => {
    const routes = dashboardRoutes({ invited: [GROUP] });
    apiFetch.mockImplementation((url) =>
      url.startsWith('/api/v1/collections/') ? refused() : routes(url)
    );
    renderHome();

    expect(await screen.findByText("Couldn't load this section")).toBeInTheDocument();
    expect(screen.getByText('Bibliocoses')).toBeInTheDocument();
    // Not the connection banner: the connection worked, the answer was an error.
    expect(screen.queryByText('Connection problem')).not.toBeInTheDocument();

    mockDashboard({ mine: [MINE], invited: [GROUP] });
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));

    expect(await screen.findByText('My workshop')).toBeInTheDocument();
    expect(screen.queryByText("Couldn't load this section")).not.toBeInTheDocument();
  });
});

describe('HomePage — invitations waiting for an answer', () => {
  const TOOLS = {
    accept_code: 'ACC001',
    reject_code: 'REJ001',
    owner_name: 'Lele',
    collection_headline: 'Tools',
  };
  const BOOKS = {
    accept_code: 'ACC002',
    reject_code: 'REJ002',
    owner_name: 'Lili',
    collection_headline: 'Books',
  };

  test('dismissing one removes that one and leaves the other waiting', async () => {
    mockDashboard({ mine: [MINE], invitations: [TOOLS, BOOKS] });
    renderHome();
    await screen.findByText('Tools');
    expect(screen.getByText('Books')).toBeInTheDocument();

    fireEvent.click(screen.getAllByRole('button', { name: 'Dismiss' })[0]);

    await waitFor(() => expect(screen.queryByText('Tools')).not.toBeInTheDocument());
    expect(screen.getByText('Books')).toBeInTheDocument();
    // Still answerable: the remaining card keeps its own accept link.
    expect(screen.getByRole('link', { name: 'Accept invitation' })).toHaveAttribute(
      'href',
      '/verify/ACC002'
    );
  });
});

describe('HomePage — collections that are switched off', () => {
  const SHED = { ...GROUP, code: 'COL002', headline: 'Old shed', status: 'INACTIVE' };

  test('they are listed apart, after the active ones, under their own heading', async () => {
    mockDashboard({ mine: [MINE, SHED] });
    renderHome();

    await screen.findByText('Old shed');
    expect(screen.getByRole('heading', { level: 2, name: 'Inactive collections' })).toBeVisible();
    const active = screen.getByText('My workshop');
    const inactive = screen.getByText('Old shed');
    expect(
      active.compareDocumentPosition(inactive) & Node.DOCUMENT_POSITION_FOLLOWING
    ).toBeTruthy();
  });

  test('a group with nothing switched off shows no such heading', async () => {
    mockDashboard({ mine: [MINE] });
    renderHome();

    await screen.findByText('My workshop');
    expect(screen.queryByRole('heading', { name: 'Inactive collections' })).not.toBeInTheDocument();
  });
});

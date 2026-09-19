import { render, screen } from '@testing-library/react';
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

function mockDashboard({ mine = [], invited = [] }) {
  apiFetch.mockImplementation((url) => {
    if (url.startsWith('/api/v1/auth/me/')) return ok(USER);
    if (url.startsWith('/api/v1/collections/')) return ok({ results: mine });
    if (url.startsWith('/api/v1/invited-collections/')) return ok(invited);
    return ok([]);
  });
}

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

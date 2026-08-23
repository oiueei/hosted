import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router';
import { vi, describe, test, expect, beforeEach } from 'vitest';

window.scrollTo = vi.fn();

vi.mock('../services/api', () => ({
  apiFetch: vi.fn(),
  getCsrfToken: vi.fn(() => 'mock-csrf'),
}));

import { apiFetch } from '../services/api';
import UserPage from '../pages/UserPage';

const ok = (body) => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });

const ME = {
  code: 'ME0001',
  name: 'Carlos',
  email: 'me@test.com',
  koro: 'basic',
  created: '2026-01-01',
};
const OTHER = { code: 'OTH001', name: 'Lili', created: '2026-01-01', shared_collections: [] };

const setApi = ({ memberships = [], profile = ME, invitedOk = true } = {}) => {
  apiFetch.mockImplementation((url) => {
    if (url.startsWith('/api/v1/invited-collections/')) {
      return invitedOk
        ? ok(memberships)
        : Promise.resolve({ ok: false, status: 500, json: async () => ({}) });
    }
    return ok(profile);
  });
};

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem('userCode', 'ME0001');
  vi.clearAllMocks();
});

const renderOwn = () =>
  render(
    <MemoryRouter>
      <UserPage />
    </MemoryRouter>
  );
const renderOther = () =>
  render(
    <MemoryRouter initialEntries={['/OTH001']}>
      <Routes>
        <Route path="/:userCode" element={<UserPage />} />
      </Routes>
    </MemoryRouter>
  );

/**
 * "My groups" on the own profile — where leaving a group lives now.
 *
 * It used to be a link in the collection hero, third in a stack of unlabelled
 * text links under the description and the only destructive one of the three.
 * Leaving is something you do to your own membership, so it belongs with the
 * rest of your account, beside the other memberships you might weigh it against.
 */
describe('UserPage — My groups', () => {
  test('lists the groups I belong to, each with its own way out', async () => {
    setApi({
      memberships: [
        { code: 'COL001', headline: "Lili's Lending Library" },
        { code: 'COL002', headline: "Lolo's Leafy Lounge" },
      ],
    });

    renderOwn();

    expect(await screen.findByRole('heading', { name: /my groups/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: "Lili's Lending Library" })).toHaveAttribute(
      'href',
      '/collections/COL001'
    );
    const leaveLinks = screen.getAllByRole('link', { name: /leave the group/i });
    expect(leaveLinks).toHaveLength(2);
    expect(leaveLinks[0]).toHaveAttribute('href', '/collections/COL001/leave');
  });

  test('a localized group name is resolved, never raw JSON', async () => {
    setApi({
      memberships: [
        { code: 'COL003', headline: '{"en": "Mum\'s things", "es": "Las cosas de mamá"}' },
      ],
    });

    renderOwn();

    expect(await screen.findByRole('link', { name: "Mum's things" })).toBeInTheDocument();
    expect(screen.queryByText(/\{"en"/)).not.toBeInTheDocument();
  });

  test('belonging to nothing shows no section at all', async () => {
    setApi({ memberships: [] });

    renderOwn();

    await screen.findByText(/Carlos/);
    expect(screen.queryByRole('heading', { name: /my groups/i })).not.toBeInTheDocument();
  });

  test('a failed fetch costs the section, never the profile', async () => {
    setApi({ memberships: [], invitedOk: false });

    renderOwn();

    // The profile still renders; only the groups list is absent.
    expect(await screen.findByText(/Carlos/)).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: /my groups/i })).not.toBeInTheDocument();
  });

  test("somebody else's profile never shows my memberships", async () => {
    setApi({ memberships: [{ code: 'COL001', headline: 'Private business' }], profile: OTHER });

    renderOther();

    // Their profile, rendered — the assertion is about what is absent from it.
    await screen.findByText(/don't share any collections/i);
    expect(screen.queryByRole('heading', { name: /my groups/i })).not.toBeInTheDocument();
    expect(screen.queryByText('Private business')).not.toBeInTheDocument();
  });
});

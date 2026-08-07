import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { vi, describe, test, expect, beforeEach } from 'vitest';

window.scrollTo = vi.fn();

vi.mock('../services/api', () => ({
  apiFetch: vi.fn(),
  getCsrfToken: vi.fn(() => 'mock-csrf'),
}));

import { apiFetch } from '../services/api';
import SharedThingsPage from '../pages/SharedThingsPage';

const ok = (body) => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });

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
  vi.clearAllMocks();
});

const renderPage = () => render(<MemoryRouter><SharedThingsPage /></MemoryRouter>);

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
      url.startsWith('/api/v1/invited-things/') ? ok({ results: [THING], next: null }) : ok({}));

    renderPage();

    expect(await screen.findByText('A cordless drill')).toBeInTheDocument();
    expect(apiFetch).toHaveBeenCalledWith('/api/v1/invited-things/', expect.anything());
    // The card knows which collection it came from, so its links stay in context.
    expect(screen.getByRole('link', { name: /A cordless drill/ }))
      .toHaveAttribute('href', '/collections/COL001/things/THG001');
  });

  test('an empty result says so and offers the way back, not a blank page', async () => {
    apiFetch.mockImplementation(() => ok({ results: [], next: null }));

    renderPage();

    expect(await screen.findByText(/nothing has been shared in your groups yet/i)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /back to my groups/i })).toHaveAttribute('href', '/');
  });

  test('a failed load shows a persistent error, not an endless spinner', async () => {
    apiFetch.mockImplementation(() => Promise.resolve({ ok: false, status: 500, json: () => Promise.resolve({}) }));

    renderPage();

    expect(await screen.findByText(/couldn't load what's been shared/i)).toBeInTheDocument();
  });

  test('a second page is offered only when the API says there is one', async () => {
    apiFetch.mockImplementation((url) =>
      url.startsWith('/api/v1/invited-things/')
        ? ok({ results: [THING], next: 'http://testserver/api/v1/invited-things/?page=2' })
        : ok({}));

    renderPage();

    await screen.findByText('A cordless drill');
    expect(screen.getByRole('button', { name: /load more/i })).toBeInTheDocument();
  });
});

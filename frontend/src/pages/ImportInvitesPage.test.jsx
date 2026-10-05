import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route, useLocation } from 'react-router';
import { describe, test, expect, vi, beforeEach, afterEach } from 'vitest';

window.scrollTo = vi.fn();

vi.mock('../services/api', () => ({
  apiFetch: vi.fn(),
  extractApiError: vi.fn(async () => null),
  getCsrfToken: () => 'tok',
}));

import { apiFetch } from '../services/api';
import ImportInvitesPage from './ImportInvitesPage';

/**
 * The CSV of invitations has a page of its own (G2, CA 2026-10-05). It was the last
 * block of `/collections/:code/invites`, under the form that invites one address at
 * a time; CA took it off that page and put it in the collection menu, as the CSV of
 * things had been (X5), and a menu entry only links. The page is `PageLayout` — the
 * way back to "Manage members", the title — and `BulkInviteCsv`, which shows its own
 * result in place.
 */
const json = (data, ok = true, status = ok ? 200 : 400) => ({
  ok,
  status,
  json: () => Promise.resolve(data),
});

const COLLECTION = { code: 'COL001', headline: 'The lending library', language: '' };

function mockApi({ collection = json(COLLECTION), bulk = json({ invited: 2, skipped: [] }) } = {}) {
  apiFetch.mockImplementation((url, options) => {
    if (options?.method === 'POST' && url.includes('/invite/bulk/')) return Promise.resolve(bulk);
    return Promise.resolve(collection);
  });
}

function MembersProbe() {
  const { pathname } = useLocation();
  return <div data-testid="members-page">{pathname}</div>;
}

const renderPage = (entry = '/collections/COL001/invites/import') =>
  render(
    <MemoryRouter initialEntries={[entry]}>
      <Routes>
        <Route path="/collections/:code/invites/import" element={<ImportInvitesPage />} />
        <Route path="/collections/:code/invites" element={<MembersProbe />} />
      </Routes>
    </MemoryRouter>
  );

const csv = (text) => new File([text], 'guests.csv', { type: 'text/csv' });
const fileInput = (container) => container.querySelector('input[type="file"]');
const TITLE = 'Invite many at once (CSV)';

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem('userCode', 'USR001');
  vi.clearAllMocks();
  mockApi();
});
afterEach(() => vi.restoreAllMocks());

describe('ImportInvitesPage', () => {
  test('paints the title and the tool', async () => {
    const { container } = renderPage();

    expect(await screen.findByRole('heading', { level: 1, name: TITLE })).toBeInTheDocument();
    // BulkInviteCsv's own help line, and the file picker it is made of.
    expect(
      screen.getByText(
        'Upload a CSV with an "email" column (required) and an optional "name" column.'
      )
    ).toBeInTheDocument();
    expect(fileInput(container)).not.toBeNull();
    // The tab has a title of its own, ending in the product's name like every other.
    await waitFor(() => expect(document.title).toBe('Invite many at once (CSV) — OIUEEI'));
  });

  test('the way back is "Manage members", and it goes to the list', async () => {
    renderPage();

    const back = await screen.findByRole('link', { name: /Manage members/ });
    expect(back).toHaveAttribute('href', '/collections/COL001/invites');
  });

  test('a collection it cannot read leaves the tool as it is', async () => {
    mockApi({ collection: json({}, false, 403) });
    const { container } = renderPage();

    expect(await screen.findByRole('heading', { level: 1, name: TITLE })).toBeVisible();
    expect(fileInput(container)).not.toBeNull();
    expect(screen.getByRole('link', { name: /Manage members/ })).toHaveAttribute(
      'href',
      '/collections/COL001/invites'
    );
  });

  test('puts no barrier of its own: it asks for the collection and nothing else', async () => {
    // Whoever opens the address by hand gets the tool, and the server's refusal when
    // they send (`require_collection_curator`): nothing here reads `is_curator`.
    mockApi({ collection: json({ ...COLLECTION, is_member: true, is_curator: false }) });
    const { container } = renderPage();

    await screen.findByRole('heading', { level: 1, name: TITLE });
    expect(fileInput(container)).not.toBeNull();
    expect(screen.queryByTestId('members-page')).toBeNull();
    expect(screen.queryByText(/not allowed|permission/i)).toBeNull();
    expect(apiFetch.mock.calls.map(([url]) => url)).toEqual(['/api/v1/collections/COL001/']);
  });

  test('sending the list shows the result in place, and does not reload anything', async () => {
    const { container } = renderPage();
    await screen.findByRole('heading', { level: 1, name: TITLE });

    fireEvent.change(fileInput(container), {
      target: { files: [csv('email,name\nlala@mail.com,\nlele@mail.com,LeLe')] },
    });
    fireEvent.click(await screen.findByRole('button', { name: 'Send 2 invitations' }));

    // The tool's own summary, on this page: nobody is taken anywhere.
    expect(await screen.findByText('2 invitations sent.')).toBeInTheDocument();
    expect(screen.queryByTestId('members-page')).toBeNull();
    expect(screen.getByRole('heading', { level: 1, name: TITLE })).toBeVisible();
    // The batch went to the bulk endpoint, once…
    const posts = apiFetch.mock.calls.filter(([, o]) => o?.method === 'POST');
    expect(posts).toHaveLength(1);
    expect(posts[0][0]).toBe('/api/v1/collections/COL001/invite/bulk/');
    expect(JSON.parse(posts[0][1].body)).toEqual({
      invites: [{ email: 'lala@mail.com' }, { email: 'lele@mail.com', name: 'LeLe' }],
    });
    // …and the collection was not read again: that refresh belonged to the members
    // page, which reads it afresh when the reader goes back to it.
    expect(
      apiFetch.mock.calls.filter(([url]) => url === '/api/v1/collections/COL001/')
    ).toHaveLength(1);
  });
});

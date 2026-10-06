import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route, useLocation } from 'react-router';
import { describe, test, expect, vi, beforeEach, afterEach } from 'vitest';

window.scrollTo = vi.fn();

vi.mock('../services/api', () => ({
  apiFetch: vi.fn(),
  extractApiError: vi.fn(async () => null),
  getCsrfToken: () => 'tok',
}));
// The ticketed upload path is covered in src/utils/uploadImage.test.js.
// Stub the upload and keep the real constants and error classes the component reads.
vi.mock('../utils/uploadImage', async (importOriginal) => ({
  ...(await importOriginal()),
  uploadImage: vi.fn(),
}));

import { apiFetch } from '../services/api';
import ImportThingsPage from './ImportThingsPage';

/**
 * The CSV import has a page of its own. It was a section at the
 * foot of `/collections/:code/add`; it left that page (it is already in the
 * menu), and a menu entry only links. The page is `PageLayout` — the way back, the
 * title — and `BulkAddCsv`, and after an import it goes back to the collection, as it
 * did from `/add`.
 */
const json = (data, ok = true, status = ok ? 200 : 400) => ({
  ok,
  status,
  json: () => Promise.resolve(data),
});

const COLLECTION = { code: 'COL001', headline: 'The lending library', language: '' };

function mockApi({ collection = json(COLLECTION), bulk = json({ created: 1 }) } = {}) {
  apiFetch.mockImplementation((url, options) => {
    if (options?.method === 'POST' && url.includes('/things/bulk/')) return Promise.resolve(bulk);
    return Promise.resolve(collection);
  });
}

function CollectionProbe() {
  const { pathname } = useLocation();
  return <div data-testid="collection-page">{pathname}</div>;
}

const renderPage = (entry = '/collections/COL001/import') =>
  render(
    <MemoryRouter initialEntries={[entry]}>
      <Routes>
        <Route path="/collections/:code/import" element={<ImportThingsPage />} />
        <Route path="/collections/:code" element={<CollectionProbe />} />
      </Routes>
    </MemoryRouter>
  );

const csv = (text) => new File([text], 'things.csv', { type: 'text/csv' });
const fileInput = (container) => container.querySelector('input[type="file"]');

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem('userCode', 'USR001');
  vi.clearAllMocks();
  mockApi();
});
afterEach(() => vi.restoreAllMocks());

describe('ImportThingsPage', () => {
  test('paints the title and the tool', async () => {
    const { container } = renderPage();

    expect(
      await screen.findByRole('heading', { level: 1, name: 'Add several at once (CSV)' })
    ).toBeInTheDocument();
    // BulkAddCsv's own help line, and the file picker it is made of.
    expect(
      screen.getByText('Add multiple things from a CSV — or a ZIP with the photos included.')
    ).toBeInTheDocument();
    expect(fileInput(container)).not.toBeNull();
    await waitFor(() => expect(document.title).toBe('Add several at once (CSV) — OIUEEI'));
  });

  test('the way back names the collection and goes to it', async () => {
    renderPage();

    const back = await screen.findByRole('link', { name: /The lending library/ });
    expect(back).toHaveAttribute('href', '/collections/COL001');
    expect(apiFetch).toHaveBeenCalledWith('/api/v1/collections/COL001/');
  });

  test('a collection it cannot read keeps the generic way back and the tool as it is', async () => {
    mockApi({ collection: json({}, false, 403) });
    const { container } = renderPage();

    expect(await screen.findByRole('link', { name: /Collection/ })).toHaveAttribute(
      'href',
      '/collections/COL001'
    );
    expect(fileInput(container)).not.toBeNull();
  });

  test('puts no barrier of its own: the server decides who may add things', async () => {
    // A member of a COMMUNITY group who opens the address by hand: the page works as
    // `/add` does for them, because `can_add_thing` lets them. Nothing here reads
    // `is_curator` or `is_member`, and nothing is asked but the collection's name.
    mockApi({
      collection: json({ ...COLLECTION, mode: 'COMMUNITY', is_member: true, is_curator: false }),
    });
    const { container } = renderPage();

    // The collection has been read (its name is the way back's label) — and whatever
    // a barrier would do with that answer has had its chance.
    await screen.findByRole('link', { name: /The lending library/ });
    expect(
      screen.getByRole('heading', { level: 1, name: 'Add several at once (CSV)' })
    ).toBeVisible();
    expect(screen.queryByTestId('collection-page')).toBeNull();
    expect(fileInput(container)).not.toBeNull();
    expect(screen.queryByText(/not allowed|permission/i)).toBeNull();
    expect(apiFetch.mock.calls.map(([url]) => url)).toEqual(['/api/v1/collections/COL001/']);
  });

  test('a finished import goes back to the collection', async () => {
    const { container } = renderPage();
    await screen.findByRole('heading', { level: 1, name: 'Add several at once (CSV)' });

    fireEvent.change(fileInput(container), {
      target: { files: [csv('headline,type\nCazo de acero,RENT_THING')] },
    });
    fireEvent.click(await screen.findByRole('button', { name: 'Add 1 items' }));

    expect(await screen.findByTestId('collection-page')).toHaveTextContent('/collections/COL001');
    expect(
      apiFetch.mock.calls.some(
        ([url, o]) => url === '/api/v1/collections/COL001/things/bulk/' && o?.method === 'POST'
      )
    ).toBe(true);
  });
});

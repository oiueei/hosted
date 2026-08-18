import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router';
import { describe, test, expect, vi, beforeEach, afterEach } from 'vitest';

window.scrollTo = vi.fn();

const navigate = vi.fn();
vi.mock('react-router', async () => ({
  ...(await vi.importActual('react-router')),
  useNavigate: () => navigate,
}));

vi.mock('../services/api', () => ({
  apiFetch: vi.fn(),
  extractApiError: vi.fn(async () => null),
  getCsrfToken: () => 'tok',
}));

import { apiFetch } from '../services/api';
import EditCollectionPage from './EditCollectionPage';

// `collectionForm.test.jsx` covers the shape of this form (which fields are
// visible, which fold into "More options", the pause section). These cover the
// two owner tools hanging off the bottom of it, both of which fail in ways the
// owner has to be able to read: a save the backend refuses because narrowing
// the type list would orphan things, and the stats download.

const COLLECTION = {
  code: 'COL001',
  headline: 'Kitchen Collection',
  description: 'Things from the kitchen',
  mode: 'PROPRIETARY',
  status: 'ACTIVE',
  visibility: 'PRIVATE',
  allowed_thing_types: ['GIFT_THING'],
  rental_durations: [],
  rental_weekdays: [],
  tags: [],
  is_paused: false,
};

function mockApi({ save = { ok: true }, stats = { ok: true } } = {}) {
  apiFetch.mockImplementation((url, opts) => {
    if (opts?.method === 'PATCH') {
      return Promise.resolve({
        ok: save.ok,
        status: save.status ?? (save.ok ? 200 : 400),
        json: async () => save.body ?? {},
      });
    }
    if (url.includes('/stats/')) {
      return Promise.resolve({
        ok: stats.ok,
        status: stats.ok ? 200 : 500,
        blob: async () => new Blob(['metric,value\nmembers,3\n'], { type: 'text/csv' }),
      });
    }
    return Promise.resolve({ ok: true, status: 200, json: async () => COLLECTION });
  });
}

const renderPage = () =>
  render(
    <MemoryRouter initialEntries={['/collections/COL001/edit']}>
      <Routes>
        <Route path="/collections/:code/edit" element={<EditCollectionPage />} />
      </Routes>
    </MemoryRouter>
  );

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem('userCode', 'USR001');
  vi.clearAllMocks();
  // jsdom implements neither, and the download path calls both.
  URL.createObjectURL = vi.fn(() => 'blob:fake');
  URL.revokeObjectURL = vi.fn();
});
afterEach(() => vi.restoreAllMocks());

describe('EditCollectionPage — saving', () => {
  test('a successful save returns to the collection', async () => {
    mockApi();
    renderPage();
    await screen.findByDisplayValue('Kitchen Collection');

    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(navigate).toHaveBeenCalledWith('/collections/COL001'));
  });

  test('a narrowing that would orphan things shows which types, not "Error saving"', async () => {
    // The backend refuses to drop a type while things of that type still live
    // here, and its message names them. Swallowing it for a generic error would
    // leave the owner with a save that fails and nothing to act on — they can't
    // guess which of four types is the blocker.
    mockApi({
      save: {
        ok: false,
        status: 400,
        body: { non_field_errors: ['Remove the LEND_THING items first: 3 would be orphaned.'] },
      },
    });
    renderPage();
    await screen.findByDisplayValue('Kitchen Collection');
    navigate.mockClear();

    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    expect(
      await screen.findByText('Remove the LEND_THING items first: 3 would be orphaned.')
    ).toBeInTheDocument();
    expect(screen.queryByText('Error saving.')).toBeNull();
    expect(navigate).not.toHaveBeenCalled();
  });

  test('a 400 with a DRF `detail` is surfaced the same way', async () => {
    mockApi({ save: { ok: false, status: 400, body: { detail: 'That headline is too long.' } } });
    renderPage();
    await screen.findByDisplayValue('Kitchen Collection');

    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    expect(await screen.findByText('That headline is too long.')).toBeInTheDocument();
  });

  test('a 400 with nothing readable in it still says something', async () => {
    mockApi({ save: { ok: false, status: 400, body: {} } });
    renderPage();
    await screen.findByDisplayValue('Kitchen Collection');

    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    expect(await screen.findByText('Error saving.')).toBeInTheDocument();
  });

  test('a rate-limited save says "too many", not "error"', async () => {
    mockApi({ save: { ok: false, status: 429 } });
    renderPage();
    await screen.findByDisplayValue('Kitchen Collection');

    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    expect(await screen.findByText(/[Tt]oo many/)).toBeInTheDocument();
  });
});

describe('EditCollectionPage — the stats download', () => {
  test('downloading names the file after the collection', async () => {
    mockApi();
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    renderPage();
    await screen.findByDisplayValue('Kitchen Collection');

    fireEvent.click(screen.getByRole('button', { name: 'Download stats (CSV)' }));

    await waitFor(() => expect(click).toHaveBeenCalled());
    expect(URL.createObjectURL).toHaveBeenCalled();
    // Released again: an owner may download this repeatedly from one page load,
    // and every un-revoked blob URL pins its data for the life of the document.
    await waitFor(() => expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:fake'));
  });

  test('a failed download says so instead of silently doing nothing', async () => {
    // A click that produces no file and no message reads as a broken button.
    mockApi({ stats: { ok: false } });
    renderPage();
    await screen.findByDisplayValue('Kitchen Collection');

    fireEvent.click(screen.getByRole('button', { name: 'Download stats (CSV)' }));

    expect(await screen.findByText("Couldn't download the stats.")).toBeInTheDocument();
  });

  test('the error clears when a later download succeeds', async () => {
    let failing = true;
    apiFetch.mockImplementation((url) => {
      if (url.includes('/stats/')) {
        return Promise.resolve({
          ok: !failing,
          status: failing ? 500 : 200,
          blob: async () => new Blob(['metric,value\n']),
        });
      }
      return Promise.resolve({ ok: true, status: 200, json: async () => COLLECTION });
    });
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    renderPage();
    await screen.findByDisplayValue('Kitchen Collection');

    fireEvent.click(screen.getByRole('button', { name: 'Download stats (CSV)' }));
    await screen.findByText("Couldn't download the stats.");

    failing = false;
    fireEvent.click(screen.getByRole('button', { name: 'Download stats (CSV)' }));

    await waitFor(() => expect(screen.queryByText("Couldn't download the stats.")).toBeNull());
  });
});

describe('EditCollectionPage — a deployment that has narrowed since', () => {
  /* A collection opened while COMMUNITY was on offer, on a deployment that has
     since stopped handing it out. The server judges only a **change**, so this
     owner may still save it as it stands — and the form has to keep saying so.

     The bug this pins: the filter keyed on the live `mode` state rather than
     the stored one, so the moment the owner clicked the other radio to compare,
     COMMUNITY stopped being "current", failed `isOfferable`, and unmounted.
     There was then no way back to the mode the collection was actually in
     without reloading the page — a form that had quietly become unable to
     express the row it was editing. Invisible upstream, where nothing is
     withheld, which is exactly why it needs a test. */
  const COMMUNITY_COLLECTION = { ...COLLECTION, mode: 'COMMUNITY' };

  function mockNarrowedApi() {
    apiFetch.mockImplementation((url) => {
      if (url.includes('/auth/me/')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => ({
            capabilities: {
              collection_modes: ['PROPRIETARY'],
              thing_types: ['GIFT_THING', 'SELL_THING'],
              request_url: 'https://example.org/request-access/',
            },
          }),
        });
      }
      return Promise.resolve({ ok: true, status: 200, json: async () => COMMUNITY_COLLECTION });
    });
  }

  beforeEach(() => {
    // The capabilities cache is module-scope and keyed by account; a fresh code
    // keeps these independent of the tests above without a reset export.
    localStorage.setItem('userCode', `NARROW${Math.random()}`);
    mockNarrowedApi();
  });

  test('the stored mode stays on offer after the owner tries the other one', async () => {
    renderPage();
    await screen.findByDisplayValue('Kitchen Collection');

    const community = () => screen.queryByRole('radio', { name: /community/i });
    // It is offered to begin with, because the collection is in it.
    await waitFor(() => expect(community()).not.toBeNull());

    // The owner compares: clicks the mode the deployment does allow...
    fireEvent.click(screen.getByRole('radio', { name: /just mine|proprietary/i }));

    // ...and can still change their mind. This is the assertion that failed.
    expect(community()).not.toBeNull();
    fireEvent.click(community());
    expect(community()).toBeChecked();
  });
});

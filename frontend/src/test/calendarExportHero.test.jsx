import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router';
import { vi, describe, test, expect, beforeEach } from 'vitest';

window.scrollTo = vi.fn();

vi.mock('../services/api', () => ({
  apiFetch: vi.fn(() =>
    Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) })
  ),
  getCsrfToken: vi.fn(() => 'mock-csrf'),
}));

// `downloadBlob` is imperative DOM (object URL, anchor, click) with no return
// value, so the only honest assertion is on the call itself: did the click
// hand the browser the file, and under which name. `filenameFromResponse`
// stays real — it is half of what these tests pin.
vi.mock('../utils/downloadBlob', async (importOriginal) => ({
  ...(await importOriginal()),
  default: vi.fn(),
}));

import { apiFetch } from '../services/api';
import downloadBlob from '../utils/downloadBlob';
import CollectionPage from '../pages/CollectionPage';

const LEND_THING = {
  code: 'THG001',
  type: 'LEND_THING',
  headline: 'Drill',
  description: '',
  status: 'ACTIVE',
  owner: 'ABC123',
  owner_name: 'Owner',
  fee: null,
  availability: '',
  location: '',
  condition: '',
  thumbnail_url: '',
  gallery: [],
  gallery_urls: [],
  available_today: null,
  next_available: null,
  tags: [],
  collection_tags: [],
  pending_questions: 0,
  my_pending_booking: null,
  pending_booking: null,
  bookings: [],
  created: '2026-09-01T10:00:00Z',
};

// The founder-curator shape; every test overrides what it needs.
const COLLECTION = {
  code: 'COL001',
  headline: 'Tool library',
  description: '',
  status: 'ACTIVE',
  visibility: 'PRIVATE',
  mode: 'PROPRIETARY',
  owner: 'ABC123',
  owner_name: 'Owner',
  is_curator: true,
  is_member: false,
  thumbnail_url: '',
  tags: [],
  things: [LEND_THING],
  invites: [],
  is_paused: false,
  allowed_thing_types: ['LEND_THING'],
};

// A calendar-export response the way the endpoint really answers: the count
// in `X-Calendar-Events`, the filename in `Content-Disposition`, the CSV as
// a blob. A Map stands in for Headers — `.get` with exact casing is all the
// code ever reads.
const calendarResponse = ({ count = '3', filename = 'COL001-cal.csv' } = {}) => ({
  ok: true,
  status: 200,
  headers: new Map([
    ['X-Calendar-Events', count],
    ['Content-Disposition', `attachment; filename="${filename}"`],
  ]),
  blob: () => Promise.resolve(new Blob(['csv'], { type: 'text/csv' })),
});

function setApi(collection, calendar) {
  apiFetch.mockImplementation((url) => {
    if (url.includes('/inbox/')) {
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([]) });
    }
    if (url === '/api/v1/collections/COL001/calendar-export/') {
      return Promise.resolve(calendar ?? calendarResponse());
    }
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(collection) });
  });
}

function renderCollection(collection, calendar) {
  setApi(collection, calendar);
  return render(
    <MemoryRouter initialEntries={['/collections/COL001']}>
      <Routes>
        <Route path="/collections/:code" element={<CollectionPage />} />
      </Routes>
    </MemoryRouter>
  );
}

const BUTTON_NAME = 'Download reservations for your calendar (CSV)';

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem('userCode', 'ABC123');
  localStorage.setItem(
    'theeemeColors',
    JSON.stringify({
      color_01: 'bus',
      color_02: 'suomenlinna-light',
      color_03: 'copper',
      color_04: 'black',
      color_05: 'white',
      color_06: 'white',
    })
  );
  localStorage.setItem('koro', 'basic');
  vi.clearAllMocks();
});

/**
 * The calendar download, offered where a curator already manages the group
 * (CA, 2026-09-28): the hero's curator button row, next to Edit / Add /
 * Manage guests. It is the same control the edit page offers at its foot —
 * the request, the filename rule and the "only the new ones" promise live in
 * `CalendarExportButton`, so these tests pin the hero's two own decisions:
 *
 * - WHO sees it: `is_curator` only (a member or an anonymous reader has
 *   nothing to import), and only where the group actually holds date-based
 *   things — the allowlist says so when it exists, the things themselves say
 *   so for an old collection that never restricted anything.
 * - What a click does: the incremental POST (never a GET — it marks the
 *   reservations delivered) and the count-gated download.
 */
describe('CalendarExportButton in the CollectionPage hero', () => {
  test('a curator of a collection whose allowlist names a date-based type gets the button', async () => {
    renderCollection(COLLECTION);

    expect(await screen.findByRole('button', { name: BUTTON_NAME })).toBeInTheDocument();
  });

  test('a co-curator (not the founder) gets it too', async () => {
    renderCollection({
      ...COLLECTION,
      owner: 'OTHER1',
      owner_name: 'Founder',
      co_owners: [{ code: 'OTHER1', name: 'Founder Co' }],
    });

    expect(await screen.findByRole('button', { name: BUTTON_NAME })).toBeInTheDocument();
  });

  test('a curator of a GIFT/SELL-only collection gets no button — nothing there books a date', async () => {
    renderCollection({
      ...COLLECTION,
      allowed_thing_types: ['GIFT_THING', 'SELL_THING'],
      things: [{ ...LEND_THING, type: 'GIFT_THING', headline: 'Board game' }],
    });

    await screen.findByText('Board game');
    expect(screen.queryByRole('button', { name: BUTTON_NAME })).not.toBeInTheDocument();
  });

  test('a member who is not a curator gets no button, even with date-based things', async () => {
    renderCollection({
      ...COLLECTION,
      owner: 'OTHER1',
      owner_name: 'Owner',
      is_curator: false,
      is_member: true,
      mode: 'COMMUNITY',
      visibility: 'PUBLIC',
    });

    await screen.findByText('Drill');
    expect(screen.queryByRole('button', { name: BUTTON_NAME })).not.toBeInTheDocument();
  });

  test('an anonymous reader gets no button', async () => {
    localStorage.removeItem('userCode');
    // The server computes `is_curator` per reader — a stranger on a PUBLIC
    // collection is not one, so the payload it gets is not one either.
    renderCollection({ ...COLLECTION, visibility: 'PUBLIC', is_curator: false });

    await screen.findByText('Drill');
    expect(screen.queryByRole('button', { name: BUTTON_NAME })).not.toBeInTheDocument();
  });

  test('an old collection with no allowlist: a RENT thing offers the button', async () => {
    renderCollection({
      ...COLLECTION,
      allowed_thing_types: [],
      things: [{ ...LEND_THING, type: 'RENT_THING', headline: 'Projector' }],
    });

    expect(await screen.findByRole('button', { name: BUTTON_NAME })).toBeInTheDocument();
  });

  test('no allowlist and nothing date-based offers no button either', async () => {
    renderCollection({
      ...COLLECTION,
      allowed_thing_types: [],
      things: [{ ...LEND_THING, type: 'SELL_THING', headline: 'Record' }],
    });

    await screen.findByText('Record');
    expect(screen.queryByRole('button', { name: BUTTON_NAME })).not.toBeInTheDocument();
  });

  test('a click POSTs the export and saves the file under the server-set name', async () => {
    renderCollection(COLLECTION, calendarResponse({ count: '3', filename: 'COL001-cal.csv' }));

    fireEvent.click(await screen.findByRole('button', { name: BUTTON_NAME }));

    await waitFor(() => {
      expect(apiFetch).toHaveBeenCalledWith('/api/v1/collections/COL001/calendar-export/', {
        method: 'POST',
      });
      expect(downloadBlob).toHaveBeenCalledWith(expect.any(Blob), 'COL001-cal.csv');
    });
    expect(await screen.findByText('3 new event(s) — check your downloads.')).toBeInTheDocument();
  });

  test('a zero count downloads nothing and says why', async () => {
    renderCollection(COLLECTION, calendarResponse({ count: '0' }));

    fireEvent.click(await screen.findByRole('button', { name: BUTTON_NAME }));

    expect(await screen.findByText('Nothing new since your last download.')).toBeInTheDocument();
    expect(downloadBlob).not.toHaveBeenCalled();
  });
});

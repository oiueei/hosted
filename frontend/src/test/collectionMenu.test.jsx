import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
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
// in `X-Calendar-Events`, the filename in `Content-Disposition`, the .ics as
// a blob. A Map stands in for Headers — `.get` with exact casing is all the
// code ever reads.
const calendarResponse = ({ count = '3', cancelled, filename = 'COL001-cal.ics' } = {}) => ({
  ok: true,
  status: 200,
  headers: new Map([
    ['X-Calendar-Events', count],
    // Absent unless a test names it — the SPA must read a missing header as 0.
    ...(cancelled === undefined ? [] : [['X-Calendar-Cancelled', cancelled]]),
    ['Content-Disposition', `attachment; filename="${filename}"`],
  ]),
  blob: () => Promise.resolve(new Blob(['BEGIN:VCALENDAR'], { type: 'text/calendar' })),
});

// The JSON export's name comes from the server's Content-Disposition; the
// stats CSV has never had one, so its name is built client-side.
const statsResponse = () => ({
  ok: true,
  status: 200,
  blob: () => Promise.resolve(new Blob(['metric,value\n'], { type: 'text/csv' })),
});

const exportResponse = ({
  ok = true,
  status = 200,
  filename = 'oiueei-COL001-2026-08-21.json',
} = {}) => ({
  ok,
  status,
  headers: new Map(ok ? [['Content-Disposition', `attachment; filename="${filename}"`]] : []),
  blob: () => Promise.resolve(new Blob(['{}'], { type: 'application/json' })),
});

// What an endpoint answers: a response, or a function that returns one (or a
// promise of one) at each call — which is how a test makes the same download
// fail the first time and work the second, or hold it in flight.
const answer = (given, fallback) =>
  Promise.resolve(typeof given === 'function' ? given() : (given ?? fallback()));

/** The first response for the first call, the next for the next… the last for every one after. */
const sequence = (...responses) => {
  let call = 0;
  return () => responses[Math.min(call++, responses.length - 1)];
};

function setApi(collection, { calendar, stats, collectionExport } = {}) {
  apiFetch.mockImplementation((url) => {
    if (url.includes('/inbox/')) {
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([]) });
    }
    if (url === '/api/v1/collections/COL001/calendar-export/') {
      return answer(calendar, calendarResponse);
    }
    if (url === '/api/v1/collections/COL001/stats/') {
      return answer(stats, statsResponse);
    }
    if (url === '/api/v1/collections/COL001/export/') {
      return answer(collectionExport, exportResponse);
    }
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(collection) });
  });
}

function renderCollection(collection, responses) {
  setApi(collection, responses);
  return renderPage();
}

/** For tests that need their own fetch mock: they set it, then render. */
function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/collections/COL001']}>
      <Routes>
        <Route path="/collections/:code" element={<CollectionPage />} />
      </Routes>
    </MemoryRouter>
  );
}

const TRIGGER = 'Collection options';
/** The open panel, or null when it is closed. "Add thing" is also a button in the
 * hero row now (CA, 2026-10-04), so a link of that name no longer tells the two apart. */
const panel = () => document.getElementById('collection-menu-panel');
const CALENDAR = 'Download the calendar (ICS)';

/** The menu's trigger, then the panel open — every test below starts here. */
async function openMenu() {
  fireEvent.click(await screen.findByRole('button', { name: TRIGGER }));
}

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
 * The collection's own options, one click from its page (CA, 2026-10-03):
 * "Add thing", "Manage members" and the three downloads left the hero row
 * (which keeps "Edit collection" alone) and the settings page's foot, and
 * live in this menu instead — a fourth icon in the hero's corner, curators
 * only. These tests pin the menu's own decisions:
 *
 * - WHO sees it: `is_curator` only — a member or an anonymous reader gets no
 *   trigger at all, so no entry either.
 * - The calendar entry additionally needs the group to hold date-based
 *   things — the allowlist says so when it exists, the things themselves say
 *   so for an old collection that never restricted anything (the rule the
 *   hero button always used, unchanged).
 * - What a click does: each download's request, filename and outcome message
 *   (stats and JSON moved from `EditCollectionPage` as they were), the panel
 *   closing, and the focus landing back on the trigger — the pressed button
 *   disappears with the panel, and the focus would fall to <body>.
 */
describe('the collection menu in the CollectionPage hero corner', () => {
  test('a curator gets the trigger; the panel holds both links and the three downloads', async () => {
    renderCollection(COLLECTION);
    await openMenu();

    expect(within(panel()).getByRole('link', { name: 'Add thing' })).toHaveAttribute(
      'href',
      '/collections/COL001/add'
    );
    expect(screen.getByRole('link', { name: 'Manage members' })).toHaveAttribute(
      'href',
      '/collections/COL001/invites'
    );
    expect(screen.getByRole('button', { name: CALENDAR })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Download the stats (CSV)' })).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Download the whole collection (JSON)' })
    ).toBeInTheDocument();
  });

  test('the trigger draws the document-group icon, hidden from assistive tech', async () => {
    renderCollection(COLLECTION);
    const trigger = await screen.findByRole('button', { name: TRIGGER });

    // HDS names each icon's <svg> after itself (`document-group`, `menu-dots`)
    // even when `aria-hidden` keeps it out of the accessibility tree, so that
    // label is how a test tells one icon from another in jsdom.
    const icon = trigger.querySelector('svg');
    expect(icon).toHaveAttribute('aria-label', 'document-group');
    // HDS hides a bare icon by default, so this pins the outcome (the glyph is
    // never read out beside the button's own name), not the explicit prop.
    expect(icon).toHaveAttribute('aria-hidden', 'true');
    // The button's own name is still the one `aria-label`, not the icon's.
    expect(trigger).toHaveAccessibleName(TRIGGER);
  });

  test('"Add several at once (CSV)" follows "Add thing" in the panel, and goes to the bulk section', async () => {
    renderCollection(COLLECTION);
    await openMenu();

    const entries = within(panel())
      .getAllByRole('link')
      .map((link) => [link.textContent, link.getAttribute('href')]);
    expect(entries).toEqual([
      ['Add thing', '/collections/COL001/add'],
      ['Add several at once (CSV)', '/collections/COL001/add#bulk-add'],
      ['Manage members', '/collections/COL001/invites'],
    ]);
  });

  test('choosing the CSV entry closes the panel', async () => {
    renderCollection(COLLECTION);
    await openMenu();
    // jsdom would try to follow the anchor's href and say it cannot.
    const noNavigation = (event) => event.preventDefault();
    document.addEventListener('click', noNavigation);
    try {
      fireEvent.click(within(panel()).getByRole('link', { name: 'Add several at once (CSV)' }));
    } finally {
      document.removeEventListener('click', noNavigation);
    }

    expect(panel()).toBeNull();
  });

  test('a co-curator (not the founder) gets it too', async () => {
    renderCollection({
      ...COLLECTION,
      owner: 'OTHER1',
      owner_name: 'Founder',
      co_owners: [{ code: 'OTHER1', name: 'Founder Co' }],
    });

    expect(await screen.findByRole('button', { name: TRIGGER })).toBeInTheDocument();
  });

  test('a curator of a GIFT/SELL-only collection gets the menu, but no calendar entry', async () => {
    renderCollection({
      ...COLLECTION,
      allowed_thing_types: ['GIFT_THING', 'SELL_THING'],
      things: [{ ...LEND_THING, type: 'GIFT_THING', headline: 'Board game' }],
    });

    await screen.findByText('Board game');
    await openMenu();

    expect(screen.queryByRole('button', { name: CALENDAR })).not.toBeInTheDocument();
    // The two downloads that do not depend on dates stay.
    expect(screen.getByRole('button', { name: 'Download the stats (CSV)' })).toBeInTheDocument();
  });

  test('a member who is not a curator gets no menu at all, even with date-based things', async () => {
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
    expect(screen.queryByRole('button', { name: TRIGGER })).not.toBeInTheDocument();
  });

  test('an anonymous reader gets no menu', async () => {
    localStorage.removeItem('userCode');
    // The server computes `is_curator` per reader — a stranger on a PUBLIC
    // collection is not one, so the payload it gets is not one either.
    renderCollection({ ...COLLECTION, visibility: 'PUBLIC', is_curator: false });

    await screen.findByText('Drill');
    expect(screen.queryByRole('button', { name: TRIGGER })).not.toBeInTheDocument();
  });

  test('an old collection with no allowlist: a RENT thing offers the calendar entry', async () => {
    renderCollection({
      ...COLLECTION,
      allowed_thing_types: [],
      things: [{ ...LEND_THING, type: 'RENT_THING', headline: 'Projector' }],
    });

    await openMenu();
    expect(screen.getByRole('button', { name: CALENDAR })).toBeInTheDocument();
  });

  test('no allowlist and nothing date-based offers no calendar entry either', async () => {
    renderCollection({
      ...COLLECTION,
      allowed_thing_types: [],
      things: [{ ...LEND_THING, type: 'SELL_THING', headline: 'Record' }],
    });

    await screen.findByText('Record');
    await openMenu();
    expect(screen.queryByRole('button', { name: CALENDAR })).not.toBeInTheDocument();
  });

  test('the calendar entry POSTs the export and saves the file under the server-set name', async () => {
    renderCollection(COLLECTION, {
      calendar: calendarResponse({ count: '3', filename: 'COL001-cal.ics' }),
    });
    await openMenu();

    fireEvent.click(screen.getByRole('button', { name: CALENDAR }));

    await waitFor(() => {
      expect(apiFetch).toHaveBeenCalledWith('/api/v1/collections/COL001/calendar-export/', {
        method: 'POST',
      });
      expect(downloadBlob).toHaveBeenCalledWith(expect.any(Blob), 'COL001-cal.ics');
    });
    expect(await screen.findByText('3 event(s) — check your downloads.')).toBeInTheDocument();
  });

  test('a zero calendar count downloads nothing and says why', async () => {
    renderCollection(COLLECTION, { calendar: calendarResponse({ count: '0', cancelled: '0' }) });
    await openMenu();

    fireEvent.click(screen.getByRole('button', { name: CALENDAR }));

    expect(await screen.findByText('Nothing coming up in the calendar.')).toBeInTheDocument();
    expect(downloadBlob).not.toHaveBeenCalled();
  });

  test('cancellations alone are still downloaded — importing them is what clears the calendar', async () => {
    renderCollection(COLLECTION, { calendar: calendarResponse({ count: '0', cancelled: '2' }) });
    await openMenu();

    fireEvent.click(screen.getByRole('button', { name: CALENDAR }));

    expect(
      await screen.findByText(
        'Nothing coming up, but 2 cancelled reservation(s) — import the file so your calendar can drop them.'
      )
    ).toBeInTheDocument();
    expect(downloadBlob).toHaveBeenCalledWith(expect.any(Blob), 'COL001-cal.ics');
  });

  test('confirmed and cancelled together: both are said, in one message', async () => {
    renderCollection(COLLECTION, { calendar: calendarResponse({ count: '3', cancelled: '1' }) });
    await openMenu();

    fireEvent.click(screen.getByRole('button', { name: CALENDAR }));

    expect(
      await screen.findByText(
        '3 event(s) — check your downloads. It includes 1 cancelled reservation(s), marked so your calendar can drop them.'
      )
    ).toBeInTheDocument();
    expect(downloadBlob).toHaveBeenCalledTimes(1);
  });

  test.each([
    ['429', 'Too many attempts — please wait a moment and try again.'],
    ['500', "Couldn't build the calendar file. Please try again in a moment."],
  ])(
    'a calendar export refused with %s says its own message and downloads nothing',
    async (status, message) => {
      renderCollection(COLLECTION, {
        calendar: { ok: false, status: Number(status), headers: new Map() },
      });
      await openMenu();

      fireEvent.click(screen.getByRole('button', { name: CALENDAR }));

      expect(await screen.findByText(message)).toBeInTheDocument();
      expect(downloadBlob).not.toHaveBeenCalled();
    }
  );

  test('a calendar export request that never arrives says the connection one', async () => {
    apiFetch.mockImplementation((url) => {
      if (url.includes('/inbox/')) {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([]) });
      }
      if (url === '/api/v1/collections/COL001/calendar-export/') {
        return Promise.reject(new TypeError('Failed to fetch'));
      }
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(COLLECTION) });
    });
    renderPage();
    await openMenu();

    fireEvent.click(screen.getByRole('button', { name: CALENDAR }));

    expect(await screen.findByText('Connection error.')).toBeInTheDocument();
    expect(downloadBlob).not.toHaveBeenCalled();
  });

  test('the stats entry GETs the CSV and names the file after the collection', async () => {
    renderCollection(COLLECTION, { stats: statsResponse() });
    await openMenu();

    fireEvent.click(screen.getByRole('button', { name: 'Download the stats (CSV)' }));

    await waitFor(() => {
      expect(apiFetch).toHaveBeenCalledWith('/api/v1/collections/COL001/stats/');
      expect(downloadBlob).toHaveBeenCalledWith(expect.any(Blob), 'COL001-stats.csv');
    });
  });

  test('a failed stats download says so', async () => {
    renderCollection(COLLECTION, {
      stats: { ok: false, status: 500, blob: () => Promise.resolve(new Blob(['x'])) },
    });
    await openMenu();

    fireEvent.click(screen.getByRole('button', { name: 'Download the stats (CSV)' }));

    expect(await screen.findByText("Couldn't download the stats.")).toBeInTheDocument();
  });

  test('the JSON entry GETs the export and saves it under the server-set name', async () => {
    renderCollection(COLLECTION, {
      collectionExport: exportResponse({ filename: 'oiueei-COL001-2026-08-21.json' }),
    });
    await openMenu();

    fireEvent.click(screen.getByRole('button', { name: 'Download the whole collection (JSON)' }));

    await waitFor(() => {
      expect(apiFetch).toHaveBeenCalledWith('/api/v1/collections/COL001/export/');
      expect(downloadBlob).toHaveBeenCalledWith(expect.any(Blob), 'oiueei-COL001-2026-08-21.json');
    });
  });

  test.each([
    ['429', 'Too many attempts — please wait a moment and try again.'],
    ['500', "Couldn't build the export. Please try again in a moment."],
  ])('a JSON export refused with %s says its own message', async (status, message) => {
    renderCollection(COLLECTION, {
      collectionExport: exportResponse({ ok: false, status: Number(status) }),
    });
    await openMenu();

    fireEvent.click(screen.getByRole('button', { name: 'Download the whole collection (JSON)' }));

    expect(await screen.findByText(message)).toBeInTheDocument();
  });

  test('a JSON export request that never arrives says the connection one', async () => {
    apiFetch.mockImplementation((url) => {
      if (url.includes('/inbox/')) {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([]) });
      }
      if (url === '/api/v1/collections/COL001/export/') {
        return Promise.reject(new TypeError('Failed to fetch'));
      }
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(COLLECTION) });
    });
    renderPage();
    await openMenu();

    fireEvent.click(screen.getByRole('button', { name: 'Download the whole collection (JSON)' }));

    expect(await screen.findByText('Connection error.')).toBeInTheDocument();
  });

  test('starting a download drops the message of the previous one, and it does not come back', async () => {
    // One message at a time: a finished "3 event(s)" beside a half-done stats
    // file would read as both having completed. The stats response is held in
    // flight so the test sees both moments — the old message gone while the new
    // download runs, and still gone once it lands (a status zone that merely
    // hid the old message during the download would show it again at the end).
    let release;
    renderCollection(COLLECTION, {
      stats: () =>
        new Promise((resolve) => {
          release = () => resolve(statsResponse());
        }),
    });
    await openMenu();
    fireEvent.click(screen.getByRole('button', { name: CALENDAR }));
    expect(await screen.findByText('3 event(s) — check your downloads.')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: TRIGGER }));
    fireEvent.click(screen.getByRole('button', { name: 'Download the stats (CSV)' }));

    expect(await screen.findByText('Preparing the file…')).toBeInTheDocument();
    expect(screen.queryByText('3 event(s) — check your downloads.')).toBeNull();

    release();
    await waitFor(() =>
      expect(downloadBlob).toHaveBeenCalledWith(expect.any(Blob), 'COL001-stats.csv')
    );
    await waitFor(() => expect(screen.queryByText('Preparing the file…')).toBeNull());
    expect(screen.queryByText('3 event(s) — check your downloads.')).toBeNull();
  });

  test('a stats error is gone once the next stats download succeeds', async () => {
    renderCollection(COLLECTION, {
      stats: sequence(
        { ok: false, status: 500, blob: () => Promise.resolve(new Blob(['x'])) },
        statsResponse()
      ),
    });
    await openMenu();
    fireEvent.click(screen.getByRole('button', { name: 'Download the stats (CSV)' }));
    expect(await screen.findByText("Couldn't download the stats.")).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: TRIGGER }));
    fireEvent.click(screen.getByRole('button', { name: 'Download the stats (CSV)' }));

    await waitFor(() =>
      expect(downloadBlob).toHaveBeenCalledWith(expect.any(Blob), 'COL001-stats.csv')
    );
    await waitFor(() => expect(screen.queryByText("Couldn't download the stats.")).toBeNull());
  });

  test('a JSON export error is gone once the next export succeeds', async () => {
    renderCollection(COLLECTION, {
      collectionExport: sequence(exportResponse({ ok: false, status: 500 }), exportResponse()),
    });
    await openMenu();
    fireEvent.click(screen.getByRole('button', { name: 'Download the whole collection (JSON)' }));
    expect(
      await screen.findByText("Couldn't build the export. Please try again in a moment.")
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: TRIGGER }));
    fireEvent.click(screen.getByRole('button', { name: 'Download the whole collection (JSON)' }));

    await waitFor(() =>
      expect(downloadBlob).toHaveBeenCalledWith(expect.any(Blob), 'oiueei-COL001-2026-08-21.json')
    );
    await waitFor(() =>
      expect(
        screen.queryByText("Couldn't build the export. Please try again in a moment.")
      ).toBeNull()
    );
  });

  test('while a download runs, the status zone says the file is being prepared', async () => {
    let release;
    apiFetch.mockImplementation((url) => {
      if (url.includes('/inbox/')) {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([]) });
      }
      if (url === '/api/v1/collections/COL001/stats/') {
        return new Promise((resolve) => {
          release = () => resolve(statsResponse());
        });
      }
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(COLLECTION) });
    });
    renderPage();
    await openMenu();

    fireEvent.click(screen.getByRole('button', { name: 'Download the stats (CSV)' }));

    expect(await screen.findByText('Preparing the file…')).toBeInTheDocument();
    // And its menu entry is disabled until it lands.
    fireEvent.click(screen.getByRole('button', { name: TRIGGER }));
    expect(screen.getByRole('button', { name: 'Download the stats (CSV)' })).toBeDisabled();

    release();
    await waitFor(() => expect(screen.queryByText('Preparing the file…')).toBeNull());
  });

  test('Escape closes the panel and returns focus to the trigger', async () => {
    renderCollection(COLLECTION);
    await openMenu();
    const trigger = screen.getByRole('button', { name: TRIGGER });

    fireEvent.keyDown(document, { key: 'Escape' });

    expect(panel()).toBeNull();
    expect(trigger).toHaveFocus();
  });

  test('a download closes the panel and returns focus to the trigger', async () => {
    renderCollection(COLLECTION);
    await openMenu();
    const trigger = screen.getByRole('button', { name: TRIGGER });

    fireEvent.click(screen.getByRole('button', { name: 'Download the stats (CSV)' }));

    // The panel is gone at once (the file keeps fetching underneath)…
    expect(panel()).toBeNull();
    // …and the focus did not fall to <body> with the button that held it.
    expect(trigger).toHaveFocus();
  });

  // A plain click on one of the links leaves the page, which unmounts the menu
  // whether or not the link closes it — a test with a plain click would pass
  // for the wrong reason. A modified click (a new tab) is the case that stays
  // on the page, and the one where the panel would otherwise be left open.
  test.each(['Add thing', 'Add several at once (CSV)', 'Manage members'])(
    'a click on "%s" that opens a new tab still closes the panel',
    async (name) => {
      renderCollection(COLLECTION);
      await openMenu();
      // jsdom would try to follow the anchor's href and say it cannot.
      const noNavigation = (event) => event.preventDefault();
      document.addEventListener('click', noNavigation);
      try {
        fireEvent.click(within(panel()).getByRole('link', { name }), { ctrlKey: true });
      } finally {
        document.removeEventListener('click', noNavigation);
      }

      expect(panel()).toBeNull();
      // Still on the collection's page, trigger folded.
      expect(screen.getByRole('button', { name: TRIGGER })).toHaveAttribute(
        'aria-expanded',
        'false'
      );
    }
  );

  test('opening the account menu closes the collection menu — it is a click outside', async () => {
    renderCollection(COLLECTION);
    await openMenu();

    const accountTrigger = screen.getByRole('button', { name: 'Your account' });
    fireEvent.mouseDown(accountTrigger);
    fireEvent.click(accountTrigger);

    expect(panel()).toBeNull();
    expect(screen.getByRole('link', { name: 'My profile' })).toBeInTheDocument();
  });
});

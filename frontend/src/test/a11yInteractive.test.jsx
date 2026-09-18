import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { axe, toHaveNoViolations } from 'jest-axe';
import { nestedTabStops } from './nestedInteractive';
import { MemoryRouter, Routes, Route } from 'react-router';
import { vi, describe, test, expect, beforeEach, afterEach } from 'vitest';
import InfoPopover from '../components/InfoPopover';
import InlineConfirm from '../components/InlineConfirm';

expect.extend(toHaveNoViolations);
window.scrollTo = vi.fn();

// The `region` rule checks whole-page landmark structure (needs a <main>); it is
// orthogonal to whether an opened widget is itself accessible, and once an
// overlay adds a landmark it spuriously flags the rest of the page fragment. We
// keep it enabled for the base-page scan and drop it only for the overlay scans.
const NO_REGION = { rules: { region: { enabled: false } } };

// The plain smoke suite renders every page with an EMPTY collection, so
// ThingLinkbox is never axe-scanned and the owner overlays (broadcast form, QR
// dialog) are never opened. This suite fills that gap: an owner viewing a
// POPULATED, PUBLIC collection, then opening those interactive surfaces.

const MOCK_USER = {
  code: 'ABC123',
  email: 'me@test.com',
  name: 'Owner',
  headline: '',
  about: '',
  photo: '',
  photo_url: '',
  koro: 'basic',
  notify_activity: true,
  notify_news: true,
  theeeme_colors: {
    color_01: 'bus',
    color_02: 'suomenlinna-medium-light',
    color_03: 'copper',
    color_04: 'black',
    color_05: 'black',
    color_06: 'white',
  },
};

const MOCK_THING = {
  code: 'THG001',
  type: 'GIFT_THING',
  headline: 'Test Thing',
  description: 'A test thing',
  status: 'ACTIVE',
  owner: 'ABC123',
  owner_name: 'Owner',
  fee: null,
  availability: '',
  location: '',
  condition: '',
  thumbnail_url: 'https://bucket.example.com/x.jpg',
  gallery: [],
  gallery_urls: [],
  available_today: null,
  next_available: null,
  tags: ['Vintage'],
  collection_tags: ['Vintage'],
  pending_questions: 0,
  my_pending_booking: null,
  pending_booking: null,
};

const MOCK_COLLECTION = {
  code: 'COL001',
  headline: 'Test Collection',
  description: 'A test collection',
  status: 'ACTIVE',
  mode: 'PROPRIETARY',
  visibility: 'PUBLIC',
  owner: 'ABC123',
  owner_name: 'Owner',
  is_curator: true,
  thumbnail_url: '',
  tags: ['Vintage'],
  is_member: false,
  is_paused: false,
  things: [MOCK_THING],
  invites: [{ code: 'GUE001', name: 'Guest', email: 'g@test.com' }],
};

function mockResponse(data, ok = true) {
  return { ok, status: ok ? 200 : 400, json: () => Promise.resolve(data) };
}

vi.mock('../services/api', () => ({
  apiFetch: vi.fn((url) => {
    if (url.includes('/auth/me/')) return Promise.resolve(mockResponse(MOCK_USER));
    if (url.match(/\/things\/[^/]+\/calendar\//)) return Promise.resolve(mockResponse([]));
    if (url.match(/\/collections\/[^/]+\//)) return Promise.resolve(mockResponse(MOCK_COLLECTION));
    return Promise.resolve(mockResponse({}));
  }),
  extractApiError: vi.fn(() => Promise.resolve('')),
  getCsrfToken: vi.fn(() => 'mock-csrf'),
}));

import CollectionPage from '../pages/CollectionPage';
import RequestThingPage from '../pages/RequestThingPage';
import { apiFetch } from '../services/api';

function renderCollection() {
  return render(
    <MemoryRouter initialEntries={['/collections/COL001']}>
      <Routes>
        <Route path="/collections/:code" element={<CollectionPage />} />
        <Route path="*" element={<div data-testid="navigated" />} />
      </Routes>
    </MemoryRouter>
  );
}

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem('userCode', 'ABC123');
  localStorage.setItem('theeemeColors', JSON.stringify(MOCK_USER.theeeme_colors));
  localStorage.setItem('koro', 'basic');
  vi.clearAllMocks();
});

// Nesting that predates the invariant, named per surface so it can only shrink.
// **It is empty, and that is the state to keep it in.** The 25 entries it was born
// with were all `<Link>` wrapping an HDS `<Button>` — one control, two tab stops —
// and every one of them is now `ButtonLink`. An entry that no longer matches fails
// as loudly as a new violation: a surface that has been cleaned up must lose its
// line, or the list stops describing the app and starts hiding it.
const KNOWN_NESTING = [];

describe('CollectionPage (owner, populated) — interactive a11y', () => {
  test('the populated collection with ThingLinkbox cards has no axe violations', async () => {
    const { container } = renderCollection();
    // Wait for the thing card to render (ThingLinkbox — never scanned by smoke).
    await screen.findByText('Test Thing');
    expect(await axe(container)).toHaveNoViolations();
  });

  // The populated card grid is where the `<Link><Button>` pairs live: an owner
  // sees Edit / Delete / Confirm hold on every thing, and the smoke sweep renders
  // this collection empty, so none of them reach it. axe reports nothing for the
  // shape (verified), which is how they accumulated.
  test('no tab stop on a populated card grid contains another', async () => {
    const { container } = renderCollection();
    await screen.findByText('Test Thing');

    const found = nestedTabStops(container);
    expect(
      found.filter((f) => !KNOWN_NESTING.includes(f)),
      'new nesting on the card grid — use Link + useButtonStyles'
    ).toEqual([]);
    expect(
      KNOWN_NESTING.filter((k) => !found.includes(k)),
      'KNOWN_NESTING entry no longer matches — delete it'
    ).toEqual([]);
  });

  test('a card offers one link to its thing, not two', async () => {
    // The cover photo and the headline both pointed at the same page under the
    // same name, so every card cost two tab stops to one destination and put two
    // identical entries in a screen reader's list of links. In a collection
    // showing 24 things that is 48 entries for 24 places. The headline is the one
    // that stayed; the photo still works for a pointer.
    const { container } = renderCollection();
    await screen.findByText('Test Thing');

    const toThing = [...container.querySelectorAll('a[href]')].filter((a) =>
      a.getAttribute('href').endsWith('/things/THG001')
    );
    expect(toThing).toHaveLength(2);
    expect(toThing.filter((a) => a.getAttribute('tabindex') !== '-1')).toHaveLength(1);
    expect(screen.getAllByRole('link', { name: 'Test Thing' })).toHaveLength(1);
  });

  test('the opened broadcast form has no axe violations', async () => {
    const { container } = renderCollection();
    await screen.findByText('Test Thing');

    fireEvent.click(screen.getByRole('button', { name: 'Send a message to guests' }));
    await waitFor(() => expect(container.querySelector('#broadcast-message')).toBeTruthy());

    expect(await axe(container, NO_REGION)).toHaveNoViolations();
  });

  test('the opened QR share dialog has no axe violations', async () => {
    renderCollection();
    await screen.findByText('Test Thing');

    fireEvent.click(screen.getByRole('combobox', { name: /Share collection/ }));
    fireEvent.click(await screen.findByRole('option', { name: 'QR code' }));

    // The Dialog renders in a portal on document.body.
    await waitFor(() => expect(document.querySelector('.share-qr-code')).toBeTruthy());
    expect(await axe(document.body, NO_REGION)).toHaveNoViolations();
  });
});

/**
 * The two shared disclosure widgets, scanned in the state that only exists after
 * a click. Both are generic — `InfoPopover` backs the (i) on ThingForm,
 * BulkAddCsv, BulkInviteCsv and LocalizedInfo; `InlineConfirm` is the canonical
 * consequence-confirm on ThingPage, ThingLinkbox and ThingReportFooter — so a
 * violation in either repeats across most of the app, and the page-level smoke
 * sweep only ever renders them shut.
 */
describe('shared disclosure widgets — opened-state a11y', () => {
  test('the opened InfoPopover panel has no axe violations', async () => {
    const { container } = render(
      <InfoPopover title="CSV format" id="csv-help">
        <p>One row per thing.</p>
      </InfoPopover>
    );

    fireEvent.click(screen.getByRole('button', { name: 'CSV format' }));
    await screen.findByText('One row per thing.');

    expect(await axe(container, NO_REGION)).toHaveNoViolations();
  });

  test('the expanded InlineConfirm panel has no axe violations', async () => {
    const { container } = render(
      <InlineConfirm
        triggerLabel="Report this listing"
        title="Report this listing?"
        body="The owner is told, and a moderator reads it."
        confirmLabel="Report"
        onConfirm={() => {}}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: 'Report this listing' }));
    await screen.findByText('The owner is told, and a moderator reads it.');

    expect(await axe(container, NO_REGION)).toHaveNoViolations();
  });
});

/**
 * RequestThingPage — the densest form in the app (DateInput + Select + two
 * RadioOptionGroups + TextArea), and never axe-scanned before this: the smoke
 * sweep never opens a real thing's request form, and no other suite touches
 * it. Two entirely new flows (DAY and HOUR reservations) shipped into this
 * release with no axe coverage at all (found in review, 2026-09-18). Covers
 * the plain LEND/RENT range picker, both RESERVE_THING shapes, and the
 * HOUR-unit dead-end fallback — the exact state the StatusRegion fix above
 * (RequestThingPage.jsx) targets, so a missing label or a stray live-region
 * violation on that specific Notification would be caught here too.
 */
describe('RequestThingPage — interactive a11y', () => {
  const LEND_THING = {
    code: 'LND01',
    type: 'LEND_THING',
    headline: 'Lent Bike',
    location: 'Planta 1',
    collection_code: 'COL001',
    rental_weekdays: [],
    available_today: true,
    next_available: null,
  };

  const DAY_RESERVE_THING = {
    code: 'RSV01',
    type: 'RESERVE_THING',
    headline: 'Sala polivalent',
    fee: '5.00',
    location: 'Planta 1',
    collection_code: 'COL001',
    rental_weekdays: [],
    reservation_max_days: 3,
    reservation_horizon_days: 90,
    available_today: true,
    next_available: null,
  };

  const HOUR_RESERVE_THING = {
    code: 'RSV02',
    type: 'RESERVE_THING',
    headline: 'Sala amb hores',
    location: 'Planta 1',
    collection_code: 'COL001',
    reservation_unit: 'HOUR',
    reservation_horizon_days: 90,
    reservation_min_minutes: 60,
    reservation_max_minutes: 180,
    // Wed 2026-06-03 (the fixed system date below + 2 days): both blocks open.
    opening_hours: {
      2: [
        ['10:00', '14:00'],
        ['16:00', '20:00'],
      ],
    },
    available_today: true,
    next_available: null,
  };

  function setRequestApi(thing, calendar = []) {
    apiFetch.mockImplementation((url) => {
      if (/\/things\/[^/]+\/calendar\//.test(url)) return Promise.resolve(mockResponse(calendar));
      if (/\/things\/[^/]+\/$/.test(url)) return Promise.resolve(mockResponse(thing));
      return Promise.resolve(mockResponse({}));
    });
  }

  function renderRequest(thingCode) {
    return render(
      <MemoryRouter
        initialEntries={[
          { pathname: `/collections/COL001/things/${thingCode}/request`, state: {} },
        ]}
      >
        <Routes>
          <Route
            path="/collections/:code/things/:thingCode/request"
            element={<RequestThingPage />}
          />
        </Routes>
      </MemoryRouter>
    );
  }

  beforeEach(() => {
    // A fixed Monday so the HOUR-unit fixture's Wednesday opening block is
    // reachable and inside every horizon (mirrors reservations.test.jsx).
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(new Date(2026, 5, 1, 12, 0, 0));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  test('the plain LEND/RENT date-range form has no axe violations', async () => {
    setRequestApi(LEND_THING);
    const { container } = renderRequest('LND01');
    await screen.findByText('Request: Lent Bike');

    expect(await axe(container)).toHaveNoViolations();
  });

  test('the DAY-unit RESERVE_THING form (duration select + pickup) has no axe violations', async () => {
    setRequestApi(DAY_RESERVE_THING);
    const { container } = renderRequest('RSV01');
    await screen.findByText('Reserve Sala polivalent');

    expect(await axe(container)).toHaveNoViolations();
  });

  test('the HOUR-unit form, fully opened to the start-time radios, has no axe violations', async () => {
    setRequestApi(HOUR_RESERVE_THING);
    const { container } = renderRequest('RSV02');
    await screen.findByText('Reserve Sala amb hores');

    const pickup = container.querySelector('#reservation-pickup-date-hourly');
    fireEvent.change(pickup, { target: { value: '03/06/2026' } }); // Wednesday
    fireEvent.blur(pickup);
    fireEvent.click(await screen.findByRole('radio', { name: '2 hours' }));
    await screen.findByRole('radio', { name: '10:00' });

    expect(await axe(container)).toHaveNoViolations();
  });

  test('the HOUR-unit dead-end fallback ("no start times") has no axe violations', async () => {
    setRequestApi(HOUR_RESERVE_THING, [
      {
        start_date: '2026-06-03',
        end_date: '2026-06-04',
        start_time: '10:00',
        end_time: '13:00',
      },
      {
        start_date: '2026-06-03',
        end_date: '2026-06-04',
        start_time: '16:00',
        end_time: '19:00',
      },
    ]);
    const { container } = renderRequest('RSV02');
    await screen.findByText('Reserve Sala amb hores');

    const pickup = container.querySelector('#reservation-pickup-date-hourly');
    fireEvent.change(pickup, { target: { value: '03/06/2026' } });
    fireEvent.blur(pickup);
    fireEvent.click(await screen.findByRole('radio', { name: '2 hours' }));
    await screen.findByText('No times available');

    expect(await axe(container)).toHaveNoViolations();
  });
});

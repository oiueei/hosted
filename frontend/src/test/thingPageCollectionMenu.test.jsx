import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { MemoryRouter, Routes, Route, useLocation } from 'react-router';
import { vi, describe, test, expect, beforeEach } from 'vitest';

window.scrollTo = vi.fn();

vi.mock('../services/api', () => ({
  apiFetch: vi.fn(),
  extractApiError: vi.fn(() => Promise.resolve('')),
  getCsrfToken: vi.fn(() => 'mock-csrf'),
}));
vi.mock('../utils/downloadBlob', async (importOriginal) => ({
  ...(await importOriginal()),
  default: vi.fn(),
}));

import { apiFetch } from '../services/api';
import downloadBlob from '../utils/downloadBlob';
import ThingPage from '../pages/ThingPage';

/**
 * The thing's page, read through a collection, has the same corner menu as the
 * collection's own page (X4, CA 2026-10-04): a curator's (Add thing, CSV, Manage
 * members, the downloads) or a member's (the welcome document, the summary switch,
 * leaving), and "Requests to me" first in either, for whoever receives them. What
 * the page needs to know about its collection arrives in the thing's own payload
 * (`collection_menu`) — it never loads the collection, which carries every one of
 * its things. `/things/:code`, with no collection, has no menu and nothing moved.
 */
const DOC = 'https://bucket.example.com/oiueei/documents/welcome.pdf';

const THING = {
  code: 'THG001',
  type: 'GIFT_THING',
  headline: 'Blue armchair',
  description: '',
  status: 'ACTIVE',
  owner: 'OWNER1',
  owner_name: 'Owner One',
  thumbnail_url: '',
  gallery_urls: [],
  transfer_count: 0,
  collection_code: 'COL001',
  collection_headline: 'Tool library',
};

const CURATOR_MENU = {
  is_curator: true,
  is_member: false,
  welcome_doc_url: null,
  digest_frequency: 'WEEKLY',
  is_digest_muted: false,
  has_date_things: true,
};
const MEMBER_MENU = {
  is_curator: false,
  is_member: true,
  welcome_doc_url: DOC,
  digest_frequency: 'WEEKLY',
  is_digest_muted: false,
  has_date_things: false,
};

const json = (data, status = 200) => ({
  ok: status < 400,
  status,
  json: () => Promise.resolve(data),
});

/**
 * The endpoints the page touches. `menu` is the thing's `collection_menu`; `me` is
 * `GET /auth/me/`; `answers` overrides a URL's response (a value, or a function).
 */
function setApi({ menu = CURATOR_MENU, receives = false, answers = {} } = {}) {
  apiFetch.mockImplementation((url, options) => {
    const given = answers[url];
    if (given !== undefined)
      return Promise.resolve(typeof given === 'function' ? given(options) : given);
    if (url === '/api/v1/auth/me/') return Promise.resolve(json({ receives_requests: receives }));
    if (/\/things\/[^/]+\/(faq|transfers|calendar)\//.test(url))
      return Promise.resolve(json({ results: [], transfers: [], total_transfers: 0 }));
    if (/^\/api\/v1\/things\/THG001\//.test(url))
      return Promise.resolve(json({ ...THING, collection_menu: menu }));
    if (url === '/api/v1/collections/COL001/calendar-export/') {
      return Promise.resolve({
        ok: true,
        status: 200,
        headers: new Map([
          ['X-Calendar-Events', '3'],
          ['Content-Disposition', 'attachment; filename="COL001-cal.ics"'],
        ]),
        blob: () => Promise.resolve(new Blob(['BEGIN:VCALENDAR'])),
      });
    }
    if (url === '/api/v1/collections/COL001/digest/')
      return Promise.resolve(json({ muted: JSON.parse(options.body).muted }));
    return Promise.resolve(json({}));
  });
}

function LeaveProbe() {
  const { state } = useLocation();
  return <div data-testid="leave-page">{state?.headline}</div>;
}

function renderThing(path = '/collections/COL001/things/THG001') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/collections/:code/things/:thingCode" element={<ThingPage />} />
        <Route path="/things/:thingCode" element={<ThingPage />} />
        <Route path="/collections/:code/leave" element={<LeaveProbe />} />
      </Routes>
    </MemoryRouter>
  );
}

const TRIGGER = 'Collection options';
const panel = () => document.getElementById('collection-menu-panel');
const entries = () => [...panel().querySelectorAll('a, button')].map((e) => e.textContent.trim());
const openMenu = async () => fireEvent.click(await screen.findByRole('button', { name: TRIGGER }));
const thingCalls = () =>
  apiFetch.mock.calls.filter(([url]) => /^\/api\/v1\/things\/THG001\/\?/.test(url));

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem('userCode', 'OWNER1');
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

describe('the thing page — who has the collection menu', () => {
  test('a curator has it, in the corner after the account menu, with their entries', async () => {
    setApi({ menu: CURATOR_MENU });
    const { container } = renderThing();

    const menu = await screen.findByRole('button', { name: TRIGGER });
    const account = screen.getByRole('button', { name: 'Your account' });
    expect(container.querySelector('.hero-corners')).toContainElement(menu);
    expect(account.compareDocumentPosition(menu)).toBe(Node.DOCUMENT_POSITION_FOLLOWING);

    fireEvent.click(menu);
    expect(entries()).toEqual([
      'Add thing',
      'Add several at once (CSV)',
      'Manage members',
      'Download the calendar (ICS)',
      'Download the stats (CSV)',
      'Download the whole collection (JSON)',
    ]);
    expect(within(panel()).getByRole('link', { name: 'Add thing' })).toHaveAttribute(
      'href',
      '/collections/COL001/add'
    );
  });

  test('a curator of a group with nothing by date has no calendar entry', async () => {
    setApi({ menu: { ...CURATOR_MENU, has_date_things: false } });
    renderThing();
    await openMenu();

    expect(within(panel()).queryByRole('button', { name: /calendar/i })).toBeNull();
  });

  test('a member has theirs: the document, the summary switch and leaving', async () => {
    localStorage.setItem('userCode', 'GUEST1');
    setApi({ menu: MEMBER_MENU });
    renderThing();
    await openMenu();

    expect(entries()).toEqual([
      "The group's welcome document (PDF)",
      'Mute the summary',
      'Leave the group',
    ]);
  });

  test('a reader who is neither has no menu — the server sent none', async () => {
    localStorage.setItem('userCode', 'GUEST1');
    setApi({ menu: null });
    renderThing();

    await screen.findByRole('heading', { level: 1, name: 'Blue armchair' });
    expect(screen.queryByRole('button', { name: TRIGGER })).not.toBeInTheDocument();
  });

  test('a reader with no session has no menu, whatever arrives', async () => {
    localStorage.removeItem('userCode');
    setApi({ menu: MEMBER_MENU });
    renderThing();

    await screen.findByRole('heading', { level: 1, name: 'Blue armchair' });
    expect(screen.queryByRole('button', { name: TRIGGER })).not.toBeInTheDocument();
  });

  test('/things/:code, with no collection in the address, has none and asks for none', async () => {
    setApi({ menu: CURATOR_MENU });
    renderThing('/things/THG001');

    await screen.findByRole('heading', { level: 1, name: 'Blue armchair' });
    expect(screen.queryByRole('button', { name: TRIGGER })).not.toBeInTheDocument();
    // The page reads the thing through no collection: no `?collection=` goes out.
    expect(thingCalls()).toHaveLength(0);
  });

  test('inside a collection the page reads the thing through that collection, and never loads the collection itself', async () => {
    setApi({ menu: CURATOR_MENU });
    renderThing();
    await screen.findByRole('button', { name: TRIGGER });

    expect(thingCalls().map(([url]) => url)).toEqual(['/api/v1/things/THG001/?collection=COL001']);
    expect(apiFetch.mock.calls.some(([url]) => url === '/api/v1/collections/COL001/')).toBe(false);
  });
});

describe('the thing page — "Requests to me"', () => {
  const REQUESTS = 'Requests to me';

  test.each([
    ['a curator', 'OWNER1', CURATOR_MENU],
    ['a member', 'GUEST1', MEMBER_MENU],
  ])(
    '%s who receives them has it first in the collection menu, with a divider under it',
    async (_who, userCode, menu) => {
      localStorage.setItem('userCode', userCode);
      setApi({ menu, receives: true });
      renderThing();
      await openMenu();

      await waitFor(() => expect(entries()[0]).toBe(REQUESTS));
      expect(within(panel()).getByRole('link', { name: REQUESTS })).toHaveAttribute(
        'href',
        '/owner-bookings'
      );
      expect(panel().firstElementChild.nextElementSibling).toHaveClass('collection-menu-divider');
    }
  );

  test('and the account menu no longer has it on this page', async () => {
    setApi({ menu: CURATOR_MENU, receives: true });
    renderThing();
    await screen.findByRole('button', { name: TRIGGER });

    fireEvent.click(screen.getByRole('button', { name: 'Your account' }));

    expect(screen.getByRole('link', { name: 'My requests' })).toBeInTheDocument();
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(screen.queryByRole('link', { name: REQUESTS })).not.toBeInTheDocument();
  });

  test('somebody who receives none has it in neither', async () => {
    setApi({ menu: CURATOR_MENU, receives: false });
    renderThing();
    await openMenu();
    await waitFor(() =>
      expect(apiFetch.mock.calls.some(([url]) => url === '/api/v1/auth/me/')).toBe(true)
    );

    expect(within(panel()).queryByRole('link', { name: REQUESTS })).toBeNull();
    fireEvent.mouseDown(screen.getByRole('button', { name: 'Your account' }));
    fireEvent.click(screen.getByRole('button', { name: 'Your account' }));
    expect(screen.queryByRole('link', { name: REQUESTS })).not.toBeInTheDocument();
  });

  test('a reader with no collection menu keeps it in the account menu — never in neither', async () => {
    localStorage.setItem('userCode', 'GUEST1');
    setApi({ menu: null, receives: true });
    renderThing();
    await screen.findByRole('heading', { level: 1, name: 'Blue armchair' });

    fireEvent.click(screen.getByRole('button', { name: 'Your account' }));

    expect(await screen.findByRole('link', { name: REQUESTS })).toHaveAttribute(
      'href',
      '/owner-bookings'
    );
  });

  test('on a thing read with no collection the account menu has it, as it always did', async () => {
    setApi({ menu: CURATOR_MENU, receives: true });
    renderThing('/things/THG001');
    await screen.findByRole('heading', { level: 1, name: 'Blue armchair' });

    fireEvent.click(screen.getByRole('button', { name: 'Your account' }));

    expect(await screen.findByRole('link', { name: REQUESTS })).toBeInTheDocument();
  });
});

describe('the thing page — what the menu does from here', () => {
  test('a download works from the thing’s page, and its message comes out under the hero', async () => {
    setApi({ menu: CURATOR_MENU });
    const { container } = renderThing();
    await openMenu();

    fireEvent.click(within(panel()).getByRole('button', { name: 'Download the calendar (ICS)' }));

    const message = await screen.findByText('3 event(s) — check your downloads.');
    expect(apiFetch).toHaveBeenCalledWith('/api/v1/collections/COL001/calendar-export/', {
      method: 'POST',
    });
    expect(downloadBlob).toHaveBeenCalledWith(expect.any(Blob), 'COL001-cal.ics');
    // In a live region, in the content right under the hero — before the thing itself.
    const content = container.querySelector('.page-container');
    expect(content).toContainElement(message);
    expect(message.closest('[role="status"]')).not.toBeNull();
    expect(message.compareDocumentPosition(container.querySelector('.form-grid'))).toBe(
      Node.DOCUMENT_POSITION_FOLLOWING
    );
  });

  test('a failed download says so there too', async () => {
    setApi({
      menu: CURATOR_MENU,
      answers: {
        '/api/v1/collections/COL001/stats/': {
          ok: false,
          status: 500,
          blob: () => Promise.resolve(new Blob([])),
        },
      },
    });
    renderThing();
    await openMenu();

    fireEvent.click(within(panel()).getByRole('button', { name: 'Download the stats (CSV)' }));

    expect(await screen.findByText("Couldn't download the stats.")).toBeInTheDocument();
  });

  test('a member mutes the summary from here: the POST, the message, and the entry that flips', async () => {
    localStorage.setItem('userCode', 'GUEST1');
    setApi({ menu: MEMBER_MENU });
    renderThing();
    await openMenu();

    fireEvent.click(within(panel()).getByRole('button', { name: 'Mute the summary' }));

    expect(
      await screen.findByText("Done: you won't get this group's summary any more.")
    ).toBeInTheDocument();
    const posts = apiFetch.mock.calls.filter(
      ([url, o]) => url === '/api/v1/collections/COL001/digest/' && o?.method === 'POST'
    );
    expect(posts).toHaveLength(1);
    expect(JSON.parse(posts[0][1].body)).toEqual({ muted: true });
    await openMenu();
    expect(
      within(panel()).getByRole('button', { name: 'Get the summary again' })
    ).toBeInTheDocument();
  });

  test('a member who had muted it is offered to turn it back on', async () => {
    localStorage.setItem('userCode', 'GUEST1');
    setApi({ menu: { ...MEMBER_MENU, is_digest_muted: true } });
    renderThing();
    await openMenu();

    expect(
      within(panel()).getByRole('button', { name: 'Get the summary again' })
    ).toBeInTheDocument();
  });

  test('a group that sends no summary offers nothing to mute', async () => {
    localStorage.setItem('userCode', 'GUEST1');
    setApi({ menu: { ...MEMBER_MENU, digest_frequency: 'NONE' } });
    renderThing();
    await openMenu();

    expect(entries()).toEqual(["The group's welcome document (PDF)", 'Leave the group']);
  });

  test('"Leave the group" goes to the leave page with the group’s name', async () => {
    localStorage.setItem('userCode', 'GUEST1');
    setApi({ menu: MEMBER_MENU });
    renderThing();
    await openMenu();

    fireEvent.click(within(panel()).getByRole('link', { name: 'Leave the group' }));

    expect(await screen.findByTestId('leave-page')).toHaveTextContent('Tool library');
  });
});

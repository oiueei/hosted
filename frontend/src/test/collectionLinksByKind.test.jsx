import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route, useLocation } from 'react-router';
import { vi, describe, test, expect, beforeEach, afterEach } from 'vitest';

/**
 * Every link to a collection is built from the collection's own kind
 * (`/{kind}/{code}`), wherever the app gets the kind from: a notice's payload, a
 * row's `kind`, a card's prop, a menu's prop. Without one it is the address from
 * before kinds, which still works by a redirect.
 */
vi.mock('qrcode.react', () => ({ QRCodeSVG: () => null }));
vi.mock('../services/api', () => ({
  apiFetch: vi.fn(),
  extractApiError: vi.fn(() => Promise.resolve('')),
  getCsrfToken: vi.fn(() => 'mock-csrf'),
}));

import { apiFetch } from '../services/api';
import InboxNotifications from '../components/InboxNotifications';
import CollectionLinkbox from '../components/CollectionLinkbox';
import CollectionMenu from '../components/CollectionMenu';
import ShareCollectionMenu from '../components/ShareCollectionMenu';
import ThingLinkbox from '../components/ThingLinkbox';
import { press } from './settle';

const ok = (body) => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  localStorage.setItem('userCode', 'OWNER1');
});

describe('a notice links to the collection it came from', () => {
  const inbox = async (notification) => {
    apiFetch.mockImplementation(() => ok([notification]));
    render(
      <MemoryRouter>
        <InboxNotifications />
      </MemoryRouter>
    );
    await screen.findByRole('link');
  };

  test('a group message goes to the group, at its kind’s address', async () => {
    await inbox({
      code: 'N1',
      type: 'BROADCAST',
      payload: { collection_headline: 'Tools', collection_code: 'COL001', collection_kind: 'SHED' },
      created: '2026-10-01T10:00:00Z',
    });

    expect(screen.getByRole('link')).toHaveAttribute('href', '/shed/COL001');
  });

  test('a pending recommendation goes to the guest list of that kind', async () => {
    await inbox({
      code: 'N2',
      type: 'INVITE_PROPOSED',
      payload: {
        collection_headline: 'Tools',
        collection_code: 'COL001',
        collection_kind: 'LIBRARY',
        proposer_name: 'Lele',
      },
      created: '2026-10-01T10:00:00Z',
    });

    expect(screen.getByRole('link')).toHaveAttribute('href', '/library/COL001/invites');
  });

  test('a request goes to its thing through the collection’s kind', async () => {
    await inbox({
      code: 'N3',
      type: 'BOOKING_REQUESTED',
      payload: {
        thing_headline: 'Drill',
        requester_name: 'Lele',
        booking_code: 'BKG001',
        thing_code: 'THG001',
        collection_code: 'COL001',
        collection_kind: 'STALL',
      },
      created: '2026-10-01T10:00:00Z',
    });

    expect(screen.getByRole('link', { name: /drill|view/i })).toHaveAttribute(
      'href',
      '/stall/COL001/things/THG001'
    );
  });

  test('a notice with no kind keeps the address from before kinds', async () => {
    await inbox({
      code: 'N4',
      type: 'BROADCAST',
      payload: { collection_headline: 'Tools', collection_code: 'COL001' },
      created: '2026-10-01T10:00:00Z',
    });

    expect(screen.getByRole('link')).toHaveAttribute('href', '/collections/COL001');
  });
});

describe('a row of collections', () => {
  test.each([
    ['STALL', '/stall/COL001'],
    ['LIBRARY', '/library/COL001'],
    ['SHED', '/shed/COL001'],
    [undefined, '/collections/COL001'],
  ])('a %s collection links to %s', (kind, href) => {
    render(
      <MemoryRouter>
        <CollectionLinkbox collection={{ code: 'COL001', headline: 'Tools', kind }} />
      </MemoryRouter>
    );

    expect(screen.getByRole('link')).toHaveAttribute('href', href);
  });
});

describe('a row navigates in the app to its kind’s page', () => {
  test('a click on a library lands on /library/…', () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <Routes>
          <Route
            path="/"
            element={
              <CollectionLinkbox
                collection={{ code: 'COL001', headline: 'Tools', kind: 'LIBRARY' }}
              />
            }
          />
          <Route path="/library/:code" element={<p>Library page</p>} />
          <Route path="*" element={<p>Somewhere else</p>} />
        </Routes>
      </MemoryRouter>
    );

    fireEvent.click(screen.getByRole('link'));

    expect(screen.getByText('Library page')).toBeInTheDocument();
  });
});

describe('the collection menu', () => {
  const downloads = {
    calendar: { downloading: false, download: vi.fn() },
    stats: { downloading: false, download: vi.fn() },
    collectionExport: { downloading: false, download: vi.fn() },
  };

  test('a curator’s entries go to the kind’s pages', async () => {
    render(
      <MemoryRouter>
        <CollectionMenu code="COL001" kind="SHED" headline="Tools" downloads={downloads} />
      </MemoryRouter>
    );
    await press(screen.getByRole('button', { name: /collection options/i }));

    const hrefs = screen.getAllByRole('link').map((a) => a.getAttribute('href'));
    expect(hrefs).toEqual(
      expect.arrayContaining([
        '/shed/COL001/add',
        '/shed/COL001/import',
        '/shed/COL001/invites',
        '/shed/COL001/invites/import',
      ])
    );
    expect(hrefs.some((h) => h.startsWith('/collections/'))).toBe(false);
  });

  test('a member’s leave link goes to the kind’s page', async () => {
    render(
      <MemoryRouter>
        <CollectionMenu code="COL001" kind="LIBRARY" headline="Tools" isCurator={false} />
      </MemoryRouter>
    );
    await press(screen.getByRole('button', { name: /collection options/i }));

    expect(screen.getByRole('link', { name: /leave/i })).toHaveAttribute(
      'href',
      '/library/COL001/leave'
    );
  });

  test('without a kind it follows the prefix of the page it sits on', async () => {
    render(
      <MemoryRouter initialEntries={['/stall/COL001/things/THG001']}>
        <Routes>
          <Route
            path="*"
            element={
              <CollectionMenu code="COL001" headline="Tools" isCurator downloads={downloads} />
            }
          />
        </Routes>
      </MemoryRouter>
    );
    await press(screen.getByRole('button', { name: /collection options/i }));

    expect(screen.getByRole('link', { name: /manage members/i })).toHaveAttribute(
      'href',
      '/stall/COL001/invites'
    );
  });
});

describe('the share menu hands over the kind’s address', () => {
  let originalLocation;

  beforeEach(() => {
    originalLocation = window.location;
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: { href: '', origin: 'http://localhost:3000' },
    });
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText: vi.fn(() => Promise.resolve()) },
    });
  });

  afterEach(() => {
    Object.defineProperty(window, 'location', { configurable: true, value: originalLocation });
  });

  test('a PUBLIC library is copied at /library/…', async () => {
    render(
      <ShareCollectionMenu
        collectionCode="COL001"
        collectionKind="LIBRARY"
        collectionHeadline="Tools"
        isPublic
      />
    );
    fireEvent.click(screen.getByRole('button', { name: 'Share collection' }));
    fireEvent.click(screen.getByRole('button', { name: 'Copy invite link' }));

    await waitFor(() =>
      expect(navigator.clipboard.writeText).toHaveBeenCalledWith(
        'http://localhost:3000/library/COL001'
      )
    );
  });
});

describe('a thing card sends people through its collection’s kind', () => {
  function Arrived() {
    const { pathname, search } = useLocation();
    return <output data-testid="arrived">{pathname + search}</output>;
  }
  const thing = {
    code: 'THG001',
    type: 'LEND_THING',
    headline: 'Drill',
    status: 'ACTIVE',
    owner: 'OWNER1',
    owner_name: 'Owner',
    thumbnail_url: '',
    gallery_urls: [],
    transfer_count: 0,
  };

  test('the owner’s Edit and Delete, and the card’s own link', () => {
    render(
      <MemoryRouter>
        <Routes>
          <Route
            path="/"
            element={
              <ThingLinkbox
                thing={thing}
                userCode="OWNER1"
                collectionCode="COL001"
                collectionKind="LIBRARY"
                collectionHeadline="Tools"
                onUpdateThing={() => {}}
              />
            }
          />
          <Route path="*" element={<Arrived />} />
        </Routes>
      </MemoryRouter>
    );

    const hrefs = screen.getAllByRole('link').map((a) => a.getAttribute('href'));
    expect(hrefs).toContain('/library/COL001/things/THG001');
    expect(hrefs).toContain('/library/COL001/things/THG001/edit');
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }));
    expect(screen.getByTestId('arrived')).toHaveTextContent('/library/COL001/things/THG001/delete');
  });

  test('an anonymous click goes to the kind’s join page, with the thing', () => {
    localStorage.clear();
    render(
      <MemoryRouter>
        <Routes>
          <Route
            path="/"
            element={
              <ThingLinkbox
                thing={{ ...thing, owner: 'SOMEONE', type: 'GIFT_THING' }}
                userCode={null}
                collectionCode="COL001"
                collectionKind="STALL"
                collectionHeadline="Tools"
                loginToAct
                onUpdateThing={() => {}}
              />
            }
          />
          <Route path="*" element={<Arrived />} />
        </Routes>
      </MemoryRouter>
    );

    fireEvent.click(
      screen.getAllByRole('button').find((b) => /claim|take|request|get/i.test(b.textContent))
    );
    expect(screen.getByTestId('arrived')).toHaveTextContent('/stall/COL001/join?thing=THG001');
  });
});

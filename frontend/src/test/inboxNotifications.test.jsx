import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router';
import { vi, describe, test, expect, beforeEach } from 'vitest';

window.scrollTo = vi.fn();

vi.mock('../services/api', () => ({
  apiFetch: vi.fn(() =>
    Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) })
  ),
  getCsrfToken: vi.fn(() => 'mock-csrf'),
}));

import { apiFetch } from '../services/api';
import CollectionPage from '../pages/CollectionPage';
import HomePage from '../pages/HomePage';
import InboxNotifications from '../components/InboxNotifications';

const REQUEST_NOTIFICATION = {
  code: 'NOT001',
  type: 'BOOKING_REQUESTED',
  payload: {
    thing_headline: 'The drill',
    requester_name: 'Lele',
    booking_code: 'BKG001',
    thing_code: 'THG001',
    collection_code: 'COL001',
  },
  created: '2026-07-13T10:00:00Z',
};

// A notification from another collection: Home shows it, COL001's page must not.
const ELSEWHERE_NOTIFICATION = {
  code: 'NOT002',
  type: 'FAQ_QUESTION',
  payload: {
    thing_headline: 'A ladder',
    questioner_name: 'Lili',
    thing_code: 'THG009',
    collection_code: 'COL009',
  },
  created: '2026-07-13T09:00:00Z',
};

const COLLECTION = {
  code: 'COL001',
  headline: 'Toy library',
  description: 'Shared toys',
  status: 'ACTIVE',
  visibility: 'PRIVATE',
  mode: 'PROPRIETARY',
  owner: 'ABC123',
  owner_name: 'Test User',
  thumbnail_url: '',
  tags: [],
  things: [],
  invites: [],
  is_paused: false,
  allowed_thing_types: [],
};

const USER = { code: 'ABC123', name: 'Test User', email: 'me@test.com', koro: 'basic' };

const ok = (body) => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });

/** Route by URL like the real API does — the inbox filter is the point of the test. */
function setApi() {
  apiFetch.mockImplementation((url) => {
    if (url.startsWith('/api/v1/inbox/?collection=')) return ok([REQUEST_NOTIFICATION]);
    if (url.startsWith('/api/v1/inbox/')) return ok([REQUEST_NOTIFICATION, ELSEWHERE_NOTIFICATION]);
    if (url.startsWith('/api/v1/auth/me/')) return ok(USER);
    if (url.startsWith('/api/v1/collections/COL001/')) return ok(COLLECTION);
    if (url.startsWith('/api/v1/collections/')) return ok({ results: [] });
    return ok([]);
  });
}

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem('userCode', 'ABC123');
  vi.clearAllMocks();
  setApi();
});

const renderCollection = () =>
  render(
    <MemoryRouter initialEntries={['/collections/COL001']}>
      <Routes>
        <Route path="/collections/:code" element={<CollectionPage />} />
      </Routes>
    </MemoryRouter>
  );

describe('InboxNotifications (O1)', () => {
  test("the owner sees the collection's own notifications on its page", async () => {
    renderCollection();

    expect(await screen.findByText(/The drill/)).toBeInTheDocument();
    // Scoped: it asked the API for this collection only.
    expect(apiFetch).toHaveBeenCalledWith('/api/v1/inbox/?collection=COL001', expect.anything());
    // And the request deep-links the thing, so the owner can go and answer it.
    expect(screen.getByRole('link', { name: /view/i })).toHaveAttribute(
      'href',
      '/collections/COL001/things/THG001'
    );
  });

  test('a guest gets no inbox on the collection page', async () => {
    localStorage.setItem('userCode', 'GUEST1');
    renderCollection();

    await screen.findByText('Toy library');
    expect(screen.queryByText(/The drill/)).not.toBeInTheDocument();
    expect(apiFetch).not.toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/inbox/'),
      expect.anything()
    );
  });

  test('Home still shows every notification, whatever collection it came from', async () => {
    render(
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText(/The drill/)).toBeInTheDocument();
      expect(screen.getByText(/A ladder/)).toBeInTheDocument();
    });
    expect(apiFetch).toHaveBeenCalledWith('/api/v1/inbox/', expect.anything());
  });
});

/**
 * Every type the backend writes must SAY something.
 *
 * These four had no `case` in notificationLabel/notificationBody, so they fell
 * through to the BROADCAST default and rendered a card headed " — {headline}"
 * with an empty body. The decline was the worst of them: its payload carries
 * `owner_name`, so it drew a blank message apparently *from the owner*.
 *
 * The assertion that matters is the negative one — the body is not empty and is
 * not broadcast copy. Adding a Type to core/models/notification.py without a
 * matching case fails here rather than shipping a silent card.
 */
describe('InboxNotifications — every type says something', () => {
  const CASES = [
    {
      what: 'a member leaving the group tells the owner who left',
      notification: {
        code: 'NOTA01',
        type: 'MEMBER_LEFT',
        payload: {
          collection_headline: 'Toy library',
          member_name: 'Lulu',
          collection_code: 'COL001',
        },
        created: '2026-08-06T10:00:00Z',
      },
      says: [/Lulu/, /Toy library/],
      links: '/collections/COL001',
    },
    {
      what: 'a pending recommendation names the member, the guest and whose call it is',
      notification: {
        code: 'NOTA02',
        type: 'INVITE_PROPOSED',
        payload: {
          collection_headline: 'Toy library',
          collection_code: 'COL001',
          proposer_name: 'Lele',
          email: 'nou@vei.cat',
          note: 'my downstairs neighbour',
        },
        created: '2026-08-06T10:00:00Z',
      },
      says: [/Lele/, /nou@vei\.cat/, /your call/i],
      // The guest list is where the owner actually answers it.
      links: '/collections/COL001/invites',
    },
    {
      what: 'an approved recommendation tells the proposer their guest is in',
      notification: {
        code: 'NOTA03',
        type: 'INVITE_PROPOSAL_APPROVED',
        payload: {
          collection_headline: 'Toy library',
          collection_code: 'COL001',
          email: 'nou@vei.cat',
          approved: true,
        },
        created: '2026-08-06T10:00:00Z',
      },
      says: [/nou@vei\.cat/, /Toy library/],
      links: '/collections/COL001',
    },
    {
      what: 'a declined recommendation says no reason travelled with it',
      notification: {
        code: 'NOTA04',
        type: 'INVITE_PROPOSAL_DECLINED',
        payload: {
          collection_headline: 'Toy library',
          collection_code: 'COL001',
          owner_name: 'Lili',
          email: 'nou@vei.cat',
        },
        created: '2026-08-06T10:00:00Z',
      },
      says: [/nou@vei\.cat/, /nobody was contacted/i, /haven't been told why/i],
      links: '/collections/COL001',
    },
  ];

  test.each(CASES)('$what', async ({ notification, says, links }) => {
    apiFetch.mockImplementation((url) => {
      if (url.startsWith('/api/v1/inbox/')) return ok([notification]);
      if (url.startsWith('/api/v1/auth/me/')) return ok(USER);
      if (url.startsWith('/api/v1/collections/')) return ok({ results: [] });
      return ok([]);
    });

    const { container } = render(
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>
    );

    for (const phrase of says) {
      expect(await screen.findByText(phrase, { exact: false })).toBeInTheDocument();
    }
    // Not the broadcast fallback: that renders an empty body and a bare " — ".
    expect(container.textContent).not.toMatch(/\s—\s*Toy library\s*$/);
    expect(container.textContent).not.toMatch(/\{\{\w+\}\}/);
    expect(screen.getByRole('link', { name: /decide now|open the group/i })).toHaveAttribute(
      'href',
      links
    );
  });

  test('a recommendation approved before the dedicated type existed still reads right', async () => {
    // Legacy row: INVITE_PROPOSED carrying `approved: true`. Without the
    // back-compatibility branch it would read as a request to decide — telling
    // the proposer to go and approve their own recommendation.
    apiFetch.mockImplementation((url) => {
      if (url.startsWith('/api/v1/inbox/'))
        return ok([
          {
            code: 'NOTA05',
            type: 'INVITE_PROPOSED',
            payload: {
              collection_headline: 'Toy library',
              collection_code: 'COL001',
              email: 'nou@vei.cat',
              approved: true,
            },
            created: '2026-08-06T10:00:00Z',
          },
        ]);
      if (url.startsWith('/api/v1/auth/me/')) return ok(USER);
      if (url.startsWith('/api/v1/collections/')) return ok({ results: [] });
      return ok([]);
    });

    render(
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>
    );

    expect(await screen.findByText(/recommendation went through/i)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /open the group/i })).toHaveAttribute(
      'href',
      '/collections/COL001'
    );
  });
});

/**
 * Dismissing — the one thing the inbox does that no test ever did.
 *
 * `dismiss()` drops the row from state optimistically and then DELETEs it. If
 * the DELETE stops being sent, nothing looks broken: the card vanishes on
 * click, exactly as it should, and comes back on the next load — for ever. The
 * member can never clear their inbox and has no way to tell why.
 *
 * Rendered directly rather than through a page: the dismiss and its failure
 * path belong to this component, and `onNetworkError` is a prop only a direct
 * render can observe (Home turns it into an offline banner).
 */
describe('InboxNotifications — dismissing', () => {
  const renderInbox = (onNetworkError) =>
    render(
      <MemoryRouter>
        <InboxNotifications onNetworkError={onNetworkError} />
      </MemoryRouter>
    );

  test('dismissing removes the card and tells the server which one', async () => {
    renderInbox();
    await screen.findByText(/The drill/);

    fireEvent.click(screen.getAllByRole('button', { name: 'Dismiss' })[0]);

    await waitFor(() =>
      expect(apiFetch).toHaveBeenCalledWith('/api/v1/inbox/NOT001/', { method: 'DELETE' })
    );
    expect(screen.queryByText(/The drill/)).not.toBeInTheDocument();
  });

  test('dismissing one leaves the others standing', async () => {
    // The filter is by code. A predicate that matched too widely would empty
    // the whole inbox on one click, and the rows are gone server-side too.
    renderInbox();
    await screen.findByText(/A ladder/);

    fireEvent.click(screen.getAllByRole('button', { name: 'Dismiss' })[0]);

    const deletes = () => apiFetch.mock.calls.filter(([, o]) => o?.method === 'DELETE');
    await waitFor(() => expect(deletes()).toHaveLength(1));
    // Exactly one row was dropped, and it was the one clicked.
    expect(deletes()[0][0]).toBe('/api/v1/inbox/NOT001/');
    expect(screen.getByText(/A ladder/)).toBeInTheDocument();
    expect(screen.queryByText(/The drill/)).not.toBeInTheDocument();
  });

  test('a dropped connection while dismissing is reported, not swallowed', async () => {
    const onNetworkError = vi.fn();
    apiFetch.mockImplementation((url, opts) => {
      if (opts?.method === 'DELETE') return Promise.reject(new TypeError('Failed to fetch'));
      if (url.startsWith('/api/v1/inbox/')) return ok([REQUEST_NOTIFICATION]);
      return ok([]);
    });
    renderInbox(onNetworkError);
    await screen.findByText(/The drill/);

    fireEvent.click(screen.getByRole('button', { name: 'Dismiss' }));

    await waitFor(() => expect(onNetworkError).toHaveBeenCalled());
  });
});

/**
 * L2: the backend sends the bare `name`, never `display_name`, because the
 * fallback in `display_name` is the person's email address and the reader of an
 * inbox card is a co-member who is not entitled to it. So a person who never
 * filled in their profile arrives here as `''`.
 *
 * Every one of these strings interpolates the name mid-sentence, so an empty one
 * is not a cosmetic problem: the card reads " has replied to your question
 * about:" — a message from nobody. `localizedPayload` substitutes the same
 * stand-in `ThingLinkbox` has always used, and this is what pins it.
 *
 * The backend half lives in `core/tests/integration/test_member_name_privacy.py`.
 */
describe('InboxNotifications — a person with no name still has a subject', () => {
  const renderInbox = () =>
    render(
      <MemoryRouter>
        <InboxNotifications />
      </MemoryRouter>
    );

  const NAMELESS_CASES = [
    {
      what: 'an answer from an owner who never set a name',
      notification: {
        code: 'NON001',
        type: 'FAQ_ANSWERED',
        payload: { thing_headline: 'The drill', owner_name: '', thing_code: 'THG001' },
        created: '2026-08-25T10:00:00Z',
      },
    },
    {
      what: 'a question from an asker who never set a name',
      notification: {
        code: 'NON002',
        type: 'FAQ_QUESTION',
        payload: { thing_headline: 'The drill', questioner_name: '', thing_code: 'THG001' },
        created: '2026-08-25T10:00:00Z',
      },
    },
    {
      what: 'a hold accepted by an owner who never set a name',
      notification: {
        code: 'NON003',
        type: 'BOOKING_ACCEPTED',
        payload: { thing_headline: 'The drill', owner_name: '', thing_code: 'THG001' },
        created: '2026-08-25T10:00:00Z',
      },
    },
  ];

  test('a pending invitation from an owner who never set a name still names somebody', async () => {
    // Not an inbox notification — HomePage renders these from
    // `/api/v1/my-invitations/`, whose `owner_name` follows the same rule (the
    // reader is only invited so far, so the API withholds the owner's address).
    // It sits here because it is the same concern and the same page.
    apiFetch.mockImplementation((url) => {
      if (url.startsWith('/api/v1/my-invitations/'))
        return ok([
          {
            accept_code: 'tok-accept',
            reject_code: 'tok-reject',
            collection_code: 'COL001',
            collection_headline: 'Toy library',
            owner_name: '',
          },
        ]);
      if (url.startsWith('/api/v1/inbox/')) return ok([]);
      if (url.startsWith('/api/v1/auth/me/')) return ok(USER);
      if (url.startsWith('/api/v1/collections/')) return ok({ results: [] });
      return ok([]);
    });

    render(
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>
    );

    expect(await screen.findByText(/A member has invited you/)).toBeInTheDocument();
    expect(screen.queryByText(/@/)).not.toBeInTheDocument();
  });

  test.each(NAMELESS_CASES)('$what still names somebody', async ({ notification }) => {
    apiFetch.mockImplementation((url) => {
      if (url.startsWith('/api/v1/inbox/')) return ok([notification]);
      if (url.startsWith('/api/v1/auth/me/')) return ok(USER);
      return ok([]);
    });

    renderInbox();

    // The stand-in, not a blank — and above all not an email address.
    expect(await screen.findByText(/A member/)).toBeInTheDocument();
    expect(screen.queryByText(/@/)).not.toBeInTheDocument();
  });
});

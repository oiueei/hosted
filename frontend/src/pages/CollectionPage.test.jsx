import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { axe, toHaveNoViolations } from 'jest-axe';
import { MemoryRouter, Routes, Route } from 'react-router';
import { vi, describe, test, expect, beforeEach } from 'vitest';

expect.extend(toHaveNoViolations);

// The busier hero (headline + tags + owner buttons + share menu) is what S8
// adds a photo composition to on top of — HeroPhoto itself is unit-tested
// separately (HeroPhoto.test.jsx); this checks the combination doesn't
// introduce an axe violation the way the shared smoke.test.jsx fixture
// (thumbnail_url: '') never exercises.
const COLLECTION_WITH_PHOTO = {
  code: 'COL001',
  headline: 'Kitchen Collection',
  description: 'Things from the kitchen',
  status: 'ACTIVE',
  visibility: 'PRIVATE',
  mode: 'PROPRIETARY',
  owner: 'ABC123',
  owner_name: 'Test User',
  thumbnail_url: 'https://res.cloudinary.com/demo/image/upload/oiueei/collections/cover.jpg',
  tags: [],
  things: [],
  invites: [],
  is_paused: false,
  allowed_thing_types: [],
};

vi.mock('../services/api', () => ({
  apiFetch: vi.fn(() =>
    Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(COLLECTION_WITH_PHOTO) })
  ),
  getCsrfToken: vi.fn(() => 'mock-csrf'),
}));

import { apiFetch } from '../services/api';
import CollectionPage from './CollectionPage';

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem('userCode', 'ABC123');
  // Each test asserts on the exact calls it caused; without this the previous
  // test's POSTs are still in the log and `find(...)` picks the wrong one.
  vi.clearAllMocks();
});

describe('CollectionPage with a collection thumbnail', () => {
  test('renders the photo hero with no accessibility violations', async () => {
    const { container } = render(
      <MemoryRouter initialEntries={['/collections/COL001']}>
        <Routes>
          <Route path="/collections/:code" element={<CollectionPage />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(container.querySelector('.hero-photo-wrap')).toBeTruthy();
    });
    expect(container.querySelector('.form-hero--photo')).toBeTruthy();
    expect(container.querySelector('img.hero-photo')).toHaveAttribute(
      'src',
      COLLECTION_WITH_PHOTO.thumbnail_url
    );

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});

describe('CollectionPage anonymous visitor intro', () => {
  test('shows a join link for a signed-out visitor', async () => {
    localStorage.clear();
    render(
      <MemoryRouter initialEntries={['/collections/COL001']}>
        <Routes>
          <Route path="/collections/:code" element={<CollectionPage />} />
        </Routes>
      </MemoryRouter>
    );

    const link = await screen.findByRole('link', { name: /join to take part/i });
    expect(link).toHaveAttribute('href', '/collections/COL001/join');
  });

  test('does not show the join link for an authenticated visitor', async () => {
    const { container } = render(
      <MemoryRouter initialEntries={['/collections/COL001']}>
        <Routes>
          <Route path="/collections/:code" element={<CollectionPage />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(container.querySelector('.form-hero-title')).toHaveTextContent('Kitchen Collection');
    });
    expect(screen.queryByRole('link', { name: /join to take part/i })).toBeNull();
  });
});

describe('CollectionPage inactive-things grid', () => {
  // The inactive grid used to build its own inline `onUpdateThing` instead of
  // sharing the page's useCallback'd one. Both did the same work, so the bug it
  // could hide is silent: hand the wrong callback (or none) to these cards and
  // reactivating a hidden thing still POSTs and still succeeds, but the card
  // never leaves the "Inactive things" section — the owner clicks Reactivate
  // again, and again. This pins that the card's update actually reaches the
  // page's state.
  const HIDDEN_THING = {
    code: 'THG001',
    headline: 'Old blender',
    type: 'GIFT_THING',
    status: 'INACTIVE',
    owner: 'ABC123',
    owner_name: 'Test User',
    created: '2026-07-01T10:00:00Z',
    tags: [],
    gallery_urls: [],
  };
  const COLLECTION_WITH_HIDDEN = {
    ...COLLECTION_WITH_PHOTO,
    thumbnail_url: '',
    things: [HIDDEN_THING],
  };

  test('reactivating a hidden thing moves it out of the hidden section', async () => {
    const { apiFetch } = await import('../services/api');
    apiFetch.mockImplementation((url) => {
      if (url.includes('/activate/')) {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) });
      }
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve(COLLECTION_WITH_HIDDEN),
      });
    });

    render(
      <MemoryRouter initialEntries={['/collections/COL001']}>
        <Routes>
          <Route path="/collections/:code" element={<CollectionPage />} />
        </Routes>
      </MemoryRouter>
    );

    // It starts under "Hidden things", carrying the owner-only Inactive tag.
    await screen.findByRole('heading', { name: 'Inactive things' });
    expect(screen.getByText('Old blender')).toBeInTheDocument();
    expect(screen.getByText('Inactive')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Reactivate' }));

    // The section disappears with its last member — proof the card's patch
    // landed in the page's `things` state, not in a detached copy.
    await waitFor(() => {
      expect(screen.queryByRole('heading', { name: 'Inactive things' })).toBeNull();
    });
    expect(screen.queryByText('Inactive')).toBeNull();
    expect(screen.getByText('Old blender')).toBeInTheDocument();
  });
});

describe('CollectionPage digest switch', () => {
  // The per-group half of the email preferences. `User.notify_news` defaults on
  // now, and this control is what makes that defensible rather than a pre-ticked
  // opt-in (DESIGN §6): a member leaves one chatty group's summaries without
  // giving up a single transactional email. So it has to be reachable, honest
  // about its state, and it must never claim a change the server refused.
  const MEMBER_VIEW = {
    ...COLLECTION_WITH_PHOTO,
    thumbnail_url: '',
    owner: 'OTHER1',
    is_member: true,
    digest_frequency: 'WEEKLY',
    is_digest_muted: false,
  };

  function mockPage(collection, { postOk = true } = {}) {
    apiFetch.mockImplementation((url, opts) => {
      if (opts?.method === 'POST') {
        return Promise.resolve({ ok: postOk, status: postOk ? 200 : 500, json: async () => ({}) });
      }
      return Promise.resolve({ ok: true, status: 200, json: async () => collection });
    });
    return apiFetch;
  }

  function renderCollection() {
    return render(
      <MemoryRouter initialEntries={['/collections/COL001']}>
        <Routes>
          <Route path="/collections/:code" element={<CollectionPage />} />
        </Routes>
      </MemoryRouter>
    );
  }

  test('a subscribed member is told so, and offered the way out', async () => {
    mockPage(MEMBER_VIEW);
    renderCollection();

    expect(await screen.findByText("You get a summary of what's new here.")).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Turn it off' })).toBeInTheDocument();
  });

  test('muting posts the member’s choice and only then moves the label', async () => {
    const apiFetch = mockPage(MEMBER_VIEW);
    renderCollection();
    await screen.findByRole('button', { name: 'Turn it off' });

    fireEvent.click(screen.getByRole('button', { name: 'Turn it off' }));

    await waitFor(() => {
      const post = apiFetch.mock.calls.find(([, o]) => o?.method === 'POST');
      expect(post[0]).toBe('/api/v1/collections/COL001/digest/');
      expect(JSON.parse(post[1].body)).toEqual({ muted: true });
    });
    expect(await screen.findByText('Summaries from this group are off.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Turn them back on' })).toBeInTheDocument();
  });

  test('a muted member can turn them back on', async () => {
    const apiFetch = mockPage({ ...MEMBER_VIEW, is_digest_muted: true });
    renderCollection();

    fireEvent.click(await screen.findByRole('button', { name: 'Turn them back on' }));

    await waitFor(() => {
      const post = apiFetch.mock.calls.find(([, o]) => o?.method === 'POST');
      expect(JSON.parse(post[1].body)).toEqual({ muted: false });
    });
    expect(await screen.findByText("You get a summary of what's new here.")).toBeInTheDocument();
  });

  test('a failed save leaves the label telling the truth', async () => {
    // The label must follow the server, not the click. A member who is told
    // "summaries are off" while the row never changed keeps receiving them and
    // has no reason to look at this control again.
    mockPage(MEMBER_VIEW, { postOk: false });
    renderCollection();
    await screen.findByRole('button', { name: 'Turn it off' });

    fireEvent.click(screen.getByRole('button', { name: 'Turn it off' }));

    expect(await screen.findByText(/Couldn't change that/)).toBeInTheDocument();
    expect(screen.getByText("You get a summary of what's new here.")).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Turn it off' })).toBeInTheDocument();
  });

  test('a group that sends no summary shows nothing to silence', async () => {
    // DESIGN §3: there is nothing to turn off, so there is no control.
    mockPage({ ...MEMBER_VIEW, digest_frequency: 'NONE' });
    renderCollection();

    await screen.findByText('Things from the kitchen');
    expect(screen.queryByRole('button', { name: 'Turn it off' })).toBeNull();
    expect(screen.queryByText("You get a summary of what's new here.")).toBeNull();
  });

  test('the owner is not offered a switch for a digest they never receive', async () => {
    // The digest goes to `invites`; an owner changes `digest_frequency` instead.
    mockPage({ ...MEMBER_VIEW, owner: 'ABC123', is_member: false });
    renderCollection();

    await screen.findByText('Things from the kitchen');
    expect(screen.queryByRole('button', { name: 'Turn it off' })).toBeNull();
  });

  /**
   * Leaving moved out of this hero in the 2026-08 design round, to the own
   * profile's "My groups" list. Its new home is well covered (`myGroups.test`);
   * the place it left was not, so a resurrected link would put the one
   * destructive control back where it was third in a stack of unlabelled text
   * links under the description — and nothing would go red.
   *
   * Asserted against the *route*, not a label: the point is that no control
   * here leads to the leave confirm, whatever it ends up being called.
   */
  test('a member is given no way out of the group from the collection hero', async () => {
    mockPage(MEMBER_VIEW);
    const { container } = renderCollection();
    // The member-only hero controls that stayed — so this is a page where the
    // leave link *would* render, not one where the member section is missing.
    await screen.findByRole('button', { name: 'Turn it off' });

    expect(container.querySelector('a[href="/collections/COL001/leave"]')).toBeNull();
    expect(screen.queryByRole('link', { name: /leave the group/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /leave the group/i })).toBeNull();
  });
});

const PUBLIC_COMMUNITY = {
  ...COLLECTION_WITH_PHOTO,
  visibility: 'PUBLIC',
  mode: 'COMMUNITY',
  is_member: false,
  digest_frequency: 'NONE',
  allow_member_proposals: false,
};

/**
 * The signed-in half of login-to-act.
 *
 * A PUBLIC collection is readable with no account, and an anonymous reader who
 * wants to act is sent to `/collections/:code/join` — which takes an email and
 * answers with a magic link. A reader who is *already signed in* fell straight
 * through that funnel: no join page could help them, and no endpoint existed to
 * ask. Meanwhile the page offered them "Add thing" whenever the collection was
 * COMMUNITY, an action `can_add_thing` refuses without an invite — so the reader
 * with the most intent filled the form, uploaded the photos, and got a 403.
 */
describe('A signed-in visitor on a public group', () => {
  const renderPage = () =>
    render(
      <MemoryRouter initialEntries={['/collections/COL001']}>
        <Routes>
          <Route path="/collections/:code" element={<CollectionPage />} />
        </Routes>
      </MemoryRouter>
    );

  beforeEach(() => {
    localStorage.setItem('userCode', 'VISITOR1');
  });

  test('is offered a way in, and not an action the API would refuse', async () => {
    apiFetch.mockImplementation(() =>
      Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(PUBLIC_COMMUNITY) })
    );

    renderPage();

    expect(await screen.findByRole('button', { name: 'Join this group' })).toBeInTheDocument();
    expect(screen.queryByText('Add thing')).not.toBeInTheDocument();
  });

  test('joining unlocks the member controls', async () => {
    apiFetch.mockImplementation((url, options) => {
      if (options?.method === 'POST') {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) });
      }
      // The refetch after a successful join sees the membership it created.
      const joined = apiFetch.mock.calls.some((c) => c[1]?.method === 'POST');
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ ...PUBLIC_COMMUNITY, is_member: joined }),
      });
    });

    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Join this group' }));

    expect(await screen.findByText('Add thing')).toBeInTheDocument();
    expect(
      apiFetch.mock.calls.some(
        ([url, options]) => url === '/api/v1/collections/COL001/join/' && options?.method === 'POST'
      )
    ).toBe(true);
  });

  test('a member is not asked to join again', async () => {
    apiFetch.mockImplementation(() =>
      Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ ...PUBLIC_COMMUNITY, is_member: true }),
      })
    );

    renderPage();

    expect(await screen.findByText('Add thing')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Join this group' })).not.toBeInTheDocument();
  });
});

/**
 * The broadcast emails every member of the group, and an email cannot be
 * unsent. Its only test until now was an axe scan of the opened form
 * (a11yInteractive) — nothing had ever pressed the button, so nothing said when
 * it fires, when it must not, or what it reports afterwards.
 */
describe('sending a message to the whole group', () => {
  const OWNED_WITH_GUESTS = {
    code: 'COL001',
    headline: 'Kitchen Collection',
    description: 'Things from the kitchen',
    status: 'ACTIVE',
    visibility: 'PRIVATE',
    mode: 'PROPRIETARY',
    owner: 'ABC123',
    owner_name: 'Test User',
    thumbnail_url: '',
    tags: [],
    things: [],
    invites: [{ code: 'GUE001', name: 'Guest', email: 'g@test.com' }],
    is_paused: false,
    allowed_thing_types: [],
    digest_frequency: 'NONE',
    allow_member_proposals: false,
  };

  const ok = (body) => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });

  /** The collection loads; the POST answers however this test needs it to. */
  function mockPost(post) {
    apiFetch.mockImplementation((url, options) =>
      options?.method === 'POST' ? post() : ok(OWNED_WITH_GUESTS),
    );
  }

  const broadcastPosts = () =>
    apiFetch.mock.calls.filter(([url, opts]) => opts?.method === 'POST' && url.endsWith('/broadcast/'));

  const renderPage = () =>
    render(
      <MemoryRouter initialEntries={['/collections/COL001']}>
        <Routes>
          <Route path="/collections/:code" element={<CollectionPage />} />
        </Routes>
      </MemoryRouter>
    );

  async function openComposer() {
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Send a message to guests' }));
    return screen.getByLabelText(/Message/);
  }

  test('opening it and writing sends nothing, and names the cost first', async () => {
    mockPost(() => ok({}));

    const message = await openComposer();
    fireEvent.change(message, { target: { value: 'The library is closed on Monday' } });

    expect(broadcastPosts()).toHaveLength(0);
    // DESIGN §6: the broadcast carries the owner's own address as Reply-To, and
    // that is said on the way in — before the send, not in the confirmation.
    expect(screen.getByText(/see your email address/i)).toBeInTheDocument();
  });

  test('an empty message — or one made of spaces — cannot be sent', async () => {
    // Not a validation nicety: a blank group email costs every member's
    // attention and the owner's standing to ask for it again.
    mockPost(() => ok({}));

    const message = await openComposer();
    expect(screen.getByRole('button', { name: 'Send broadcast' })).toBeDisabled();

    fireEvent.change(message, { target: { value: '   ' } });
    expect(screen.getByRole('button', { name: 'Send broadcast' })).toBeDisabled();

    fireEvent.change(message, { target: { value: 'Real words' } });
    expect(screen.getByRole('button', { name: 'Send broadcast' })).not.toBeDisabled();
  });

  test('the confirmation reports the server’s own count, not the roster on screen', async () => {
    // The page knows of one invitee; the server says it reached twelve. Only the
    // server counts who was actually emailed, so a confirmation built from the
    // invite list would be a number the owner cannot act on.
    mockPost(() => ok({ message: 'Broadcast sent', recipients: 12 }));

    const message = await openComposer();
    fireEvent.change(message, { target: { value: 'The library is closed on Monday' } });
    fireEvent.click(screen.getByRole('button', { name: 'Send broadcast' }));

    expect(await screen.findByText('Broadcast sent to 12 guests.')).toBeInTheDocument();
    expect(apiFetch).toHaveBeenCalledWith(
      '/api/v1/collections/COL001/broadcast/',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ message: 'The library is closed on Monday' }),
      })
    );
    // Emptied, so the next click cannot repeat the send that just went out.
    expect(screen.getByLabelText(/Message/)).toHaveValue('');
    expect(screen.getByRole('button', { name: 'Send broadcast' })).toBeDisabled();
  });

  test('a send that fails keeps the words the owner wrote', async () => {
    // Losing the text would be the second cost of one failure: they typed it
    // once, the network dropped it, and retyping is what makes people give up.
    mockPost(() => Promise.reject(new Error('network down')));

    const message = await openComposer();
    fireEvent.change(message, { target: { value: 'The library is closed on Monday' } });
    fireEvent.click(screen.getByRole('button', { name: 'Send broadcast' }));

    expect(await screen.findByText('Connection error.')).toBeInTheDocument();
    expect(screen.getByLabelText(/Message/)).toHaveValue('The library is closed on Monday');
    expect(screen.queryByText(/Broadcast sent/)).toBeNull();
  });

  test('an impatient second press cannot send it twice', async () => {
    // The window between the click and the answer, on the one control here
    // whose double-fire mails everybody a second copy.
    let deliver;
    mockPost(() => new Promise((resolve) => {
      deliver = () => resolve({ ok: true, status: 200, json: () => Promise.resolve({ recipients: 1 }) });
    }));

    const message = await openComposer();
    fireEvent.change(message, { target: { value: 'The library is closed on Monday' } });
    fireEvent.click(screen.getByRole('button', { name: 'Send broadcast' }));

    const busy = await screen.findByRole('button', { name: 'Sending...' });
    expect(busy).toBeDisabled();
    fireEvent.click(busy);
    expect(broadcastPosts()).toHaveLength(1);

    deliver();
    expect(await screen.findByText('Broadcast sent to 1 guests.')).toBeInTheDocument();
  });
});

describe('a broadcast the server turns down', () => {
  /* Separate from the round above because this one changed the page rather than
     covering it. The daily cap (5/day, `key="user"`) is the only refusal an
     owner meets in practice, and it does not arrive in the shape this handler
     was reading: `@ratelimit(block=True)` raises, and `api_exception_handler`
     answers `{detail: …}` with a 429. The page read `data.error` alone, so the
     owner got "Error" — while the message sat unsent and nothing said that
     tomorrow would work. */
  const OWNED_WITH_GUESTS = {
    code: 'COL001',
    headline: 'Kitchen Collection',
    description: 'Things from the kitchen',
    status: 'ACTIVE',
    visibility: 'PRIVATE',
    mode: 'PROPRIETARY',
    owner: 'ABC123',
    owner_name: 'Test User',
    thumbnail_url: '',
    tags: [],
    things: [],
    invites: [{ code: 'GUE001', name: 'Guest', email: 'g@test.com' }],
    is_paused: false,
    allowed_thing_types: [],
    digest_frequency: 'NONE',
    allow_member_proposals: false,
  };

  async function sendUnder(response) {
    apiFetch.mockImplementation((url, options) =>
      options?.method === 'POST'
        ? Promise.resolve(response)
        : Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(OWNED_WITH_GUESTS) }),
    );
    render(
      <MemoryRouter initialEntries={['/collections/COL001']}>
        <Routes>
          <Route path="/collections/:code" element={<CollectionPage />} />
        </Routes>
      </MemoryRouter>
    );
    fireEvent.click(await screen.findByRole('button', { name: 'Send a message to guests' }));
    fireEvent.change(screen.getByLabelText(/Message/), {
      target: { value: 'The library is closed on Monday' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Send broadcast' }));
  }

  test('names the daily cap instead of saying "Error"', async () => {
    await sendUnder({
      ok: false,
      status: 429,
      json: () =>
        Promise.resolve({ detail: 'Too many requests. Please slow down and try again later.' }),
    });

    expect(
      await screen.findByText('Too many requests. Please slow down and try again later.'),
    ).toBeInTheDocument();
    // The words are still there to send tomorrow.
    expect(screen.getByLabelText(/Message/)).toHaveValue('The library is closed on Monday');
  });

  test('still names the view’s own refusals', async () => {
    // `{error}` is what this endpoint answers when it refuses on its own terms,
    // and reordering must not cost that.
    await sendUnder({
      ok: false,
      status: 400,
      json: () => Promise.resolve({ error: 'No invitees to broadcast to' }),
    });

    expect(await screen.findByText('No invitees to broadcast to')).toBeInTheDocument();
  });
});

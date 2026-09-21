import { readFileSync } from 'node:fs';
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react';
import { axe, toHaveNoViolations } from 'jest-axe';
import { MemoryRouter, Routes, Route } from 'react-router';
import { vi, describe, test, expect, beforeEach, afterEach } from 'vitest';

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
  is_curator: true,
  thumbnail_url: 'https://bucket.example.com/oiueei/collections/cover.jpg',
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

  /**
   * The description keeps out of the photo's third on wide screens (CA,
   * 2026-09-21): the photo is an absolute background across the right of the
   * hero and the full-width description ran over it. jsdom does no layout, so
   * what can silently break — and what is pinned here — is the contract around
   * the rule: it still matches the real DOM, and it still sits behind the
   * breakpoint below which the photo stacks under the text and there is
   * nothing to avoid (squeezing a 320px phone by a third would buy nothing).
   */
  describe('the description keeps out of the photo', () => {
    const renderPage = async (collection) => {
      apiFetch.mockImplementation(() =>
        Promise.resolve({ ok: true, status: 200, json: async () => collection })
      );
      const utils = render(
        <MemoryRouter initialEntries={['/collections/COL001']}>
          <Routes>
            <Route path="/collections/:code" element={<CollectionPage />} />
          </Routes>
        </MemoryRouter>
      );
      await screen.findByText('Things from the kitchen');
      return utils;
    };

    test('with a photo, the description is the block the rule names, inside the photo hero', async () => {
      const { container } = await renderPage({
        ...COLLECTION_WITH_PHOTO,
        description: 'Things from the kitchen',
      });

      const description = container.querySelector(
        '.form-hero--photo .markdown-text.form-hero-text'
      );
      expect(description).toHaveTextContent('Things from the kitchen');
    });

    test('without a photo, nothing is in a photo hero, so the rule cannot apply', async () => {
      const { container } = await renderPage({
        ...COLLECTION_WITH_PHOTO,
        thumbnail_url: '',
        description: 'Things from the kitchen',
      });

      expect(container.querySelector('.form-hero--photo')).toBeNull();
      expect(container.querySelector('.markdown-text.form-hero-text')).not.toBeNull();
    });

    test('the padding lives only inside the >=768px media query', () => {
      const css = readFileSync('src/App.css', 'utf8');
      const selector = '.form-hero--photo .markdown-text.form-hero-text';
      // Exactly one rule for it, and it is the one inside the breakpoint —
      // a copy outside would squeeze every phone.
      expect(css.split(selector).length - 1).toBe(1);
      const gated = new RegExp(
        String.raw`@media \(min-width: 768px\)\s*\{\s*` +
          selector.replaceAll('.', String.raw`\.`) +
          String.raw`\s*\{[^}]*padding-right:`
      );
      expect(css).toMatch(gated);
    });
  });
});

describe('CollectionPage signed-out reader', () => {
  /**
   * The hero's "This group shares its things on OIUEEI. Join to take part →"
   * line was removed (CA, 2026-09-21). A signed-out reader still reaches
   * /collections/:code/join from the action button on any card (login-to-act,
   * pinned in `thingBooking.test.jsx`); what is gone is the standing invitation
   * in the hero.
   *
   * Asserted through the link's target and the raw i18n key — the strings went
   * with the line, so a resurrected `t('collectionPage.anonIntro')` renders its
   * own key and an English-text query would pass for the wrong reason.
   */
  const PUBLIC_VIEW = {
    ...COLLECTION_WITH_PHOTO,
    thumbnail_url: '',
    visibility: 'PUBLIC',
    owner: 'OTHER1',
    is_curator: false,
    is_member: false,
  };

  test('is offered no join line in the hero', async () => {
    localStorage.clear();
    apiFetch.mockImplementation(() =>
      Promise.resolve({ ok: true, status: 200, json: async () => PUBLIC_VIEW })
    );
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
    expect(container.querySelector('a[href="/collections/COL001/join"]')).toBeNull();
    expect(container.textContent).not.toMatch(/collectionPage\.anonIntro/);
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

describe('CollectionPage member hero', () => {
  const MEMBER_VIEW = {
    ...COLLECTION_WITH_PHOTO,
    thumbnail_url: '',
    owner: 'OTHER1',
    is_member: true,
    // A plain member of somebody else's group, not a curator — override
    // rather than inherit COLLECTION_WITH_PHOTO's true.
    is_curator: false,
    digest_frequency: 'WEEKLY',
    is_digest_muted: false,
    allow_member_proposals: true,
  };

  function mockPage(collection) {
    apiFetch.mockImplementation(() =>
      Promise.resolve({ ok: true, status: 200, json: async () => collection })
    );
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

  /**
   * The per-group "You get a summary of what's new here — turn it off" line
   * left the hero (CA, 2026-09-21): a sentence about email, in the one place a
   * member comes to look at things. Muting a group is still one click from the
   * footer of every digest (`DigestMutePage`), and the endpoint behind the old
   * switch is untouched, so this is only about what the page offers.
   *
   * Asserted three ways, because each alone can be fooled: the class the block
   * carried, the raw i18n key (the strings were deleted with the block, so a
   * resurrected `t('collectionPage.digestSubscribed')` renders its own key —
   * an English-text assertion would pass for the wrong reason), and the one
   * thing the switch could do, which is send a POST.
   */
  test.each([
    ['a member of a group that sends a digest', MEMBER_VIEW],
    ['a member who had muted it', { ...MEMBER_VIEW, is_digest_muted: true }],
    [
      'a co-curator, who is still an ordinary invitee for the digest',
      { ...MEMBER_VIEW, is_member: false, is_curator: true },
    ],
  ])('%s is offered no digest switch', async (_who, view) => {
    const fetchMock = mockPage(view);
    const { container } = renderCollection();
    await screen.findByText('Things from the kitchen');

    expect(container.querySelector('.digest-pref')).toBeNull();
    expect(container.textContent).not.toMatch(/collectionPage\.digest/);
    expect(screen.queryByRole('button', { name: /turn it off|turn them back on/i })).toBeNull();
    expect(fetchMock.mock.calls.some(([, o]) => o?.method === 'POST')).toBe(false);
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
    // A member-only hero control that stayed — so this is a page where the
    // leave link *would* render, not one where the member section is missing.
    await screen.findByRole('button', { name: /Recommend them/ });

    expect(container.querySelector('a[href="/collections/COL001/leave"]')).toBeNull();
    expect(screen.queryByRole('link', { name: /leave the group/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /leave the group/i })).toBeNull();
  });
});

/**
 * The Community / Public / Private tags after the title say how a group is set
 * up — bookkeeping for whoever runs it, not something a member or a passer-by
 * needs before they have read the name (CA, 2026-09-21). Community used to show
 * to everyone; Public/Private was already curator-only. Now both are.
 */
describe('CollectionPage hero tags belong to the curators', () => {
  const COMMUNITY_PUBLIC = {
    ...COLLECTION_WITH_PHOTO,
    thumbnail_url: '',
    mode: 'COMMUNITY',
    visibility: 'PUBLIC',
    digest_frequency: 'NONE',
  };

  function renderAs(collection, { signedIn = true } = {}) {
    if (!signedIn) localStorage.removeItem('userCode');
    apiFetch.mockImplementation(() =>
      Promise.resolve({ ok: true, status: 200, json: async () => collection })
    );
    render(
      <MemoryRouter initialEntries={['/collections/COL001']}>
        <Routes>
          <Route path="/collections/:code" element={<CollectionPage />} />
        </Routes>
      </MemoryRouter>
    );
    return screen.findByRole('heading', { level: 1, name: /Kitchen Collection/ });
  }

  test('a curator sees both the mode and the visibility tag', async () => {
    const title = await renderAs({ ...COMMUNITY_PUBLIC, is_curator: true });

    expect(within(title).getByText('Community')).toBeInTheDocument();
    expect(within(title).getByText('Public')).toBeInTheDocument();
  });

  test('a curator of a private, proprietary group sees just Private', async () => {
    const title = await renderAs({
      ...COMMUNITY_PUBLIC,
      is_curator: true,
      mode: 'PROPRIETARY',
      visibility: 'PRIVATE',
    });

    expect(within(title).getByText('Private')).toBeInTheDocument();
    expect(within(title).queryByText('Community')).toBeNull();
  });

  test('a member of the same group sees the title and nothing after it', async () => {
    const title = await renderAs({
      ...COMMUNITY_PUBLIC,
      owner: 'OTHER1',
      is_curator: false,
      is_member: true,
    });

    expect(title).toHaveTextContent(/^Kitchen Collection$/);
    expect(within(title).queryByText('Community')).toBeNull();
    expect(within(title).queryByText('Public')).toBeNull();
  });

  test('an anonymous reader of a public group sees the title and nothing after it', async () => {
    const title = await renderAs(
      { ...COMMUNITY_PUBLIC, owner: 'OTHER1', is_curator: false, is_member: false },
      { signedIn: false }
    );

    expect(title).toHaveTextContent(/^Kitchen Collection$/);
    expect(within(title).queryByText('Community')).toBeNull();
    expect(within(title).queryByText('Public')).toBeNull();
  });
});

const PUBLIC_COMMUNITY = {
  ...COLLECTION_WITH_PHOTO,
  visibility: 'PUBLIC',
  mode: 'COMMUNITY',
  is_member: false,
  // Unlike COLLECTION_WITH_PHOTO's own tests, the viewer here (VISITOR1) is
  // never the owner — is_curator must say so explicitly rather than inherit
  // the spread owner's true value.
  is_curator: false,
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

  // The same dead end, one screen lower: an EMPTY community group's "no things
  // yet" line kept offering "Add one" and the CSV import to every reader of a
  // COMMUNITY collection, member or not — the hero button above was fixed and
  // this one wasn't, because nothing here had ever rendered an empty group.
  test('an empty group does not invite a non-member to fill it', async () => {
    apiFetch.mockImplementation(() =>
      Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(PUBLIC_COMMUNITY) })
    );

    renderPage();

    expect(await screen.findByText(/No things in this collection yet/)).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Add one' })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /Add several at once/ })).not.toBeInTheDocument();
  });

  test('a signed-out reader of an empty group is not sent to a form, nor offered a way in', async () => {
    localStorage.clear();
    apiFetch.mockImplementation(() =>
      Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(PUBLIC_COMMUNITY) })
    );

    renderPage();

    expect(await screen.findByText(/No things in this collection yet/)).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Add one' })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /Add several at once/ })).not.toBeInTheDocument();
    // The hero's standing "Join to take part" line is gone (CA, 2026-09-21), and
    // an empty group has no card whose action button could route them to the
    // join page — so this reader is offered no way in at all. That is the known
    // cost of removing the line, pinned so it stays a decision and cannot
    // become an accident: if a way in is added, this is the test to change.
    // By target, not by name: a resurrected line would render its raw i18n key
    // (the strings were deleted), which no /join/ name query would ever match.
    expect(document.querySelector('a[href$="/join"]')).toBeNull();
  });

  test('a member of an empty group is invited to start it', async () => {
    apiFetch.mockImplementation(() =>
      Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ ...PUBLIC_COMMUNITY, is_member: true }),
      })
    );

    renderPage();

    expect(await screen.findByRole('link', { name: 'Add one' })).toHaveAttribute(
      'href',
      '/collections/COL001/add'
    );
    expect(screen.getByRole('link', { name: /Add several at once/ })).toHaveAttribute(
      'href',
      '/collections/COL001/add#bulk-add'
    );
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
    is_curator: true,
    thumbnail_url: '',
    tags: [],
    things: [],
    invites: [{ code: 'GUE001', name: 'Guest', email: 'g@test.com' }],
    is_paused: false,
    allowed_thing_types: [],
    digest_frequency: 'NONE',
    allow_member_proposals: false,
  };

  const ok = (body) =>
    Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });

  /** The collection loads; the POST answers however this test needs it to. */
  function mockPost(post) {
    apiFetch.mockImplementation((url, options) =>
      options?.method === 'POST' ? post() : ok(OWNED_WITH_GUESTS)
    );
  }

  const broadcastPosts = () =>
    apiFetch.mock.calls.filter(
      ([url, opts]) => opts?.method === 'POST' && url.endsWith('/broadcast/')
    );

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
    mockPost(
      () =>
        new Promise((resolve) => {
          deliver = () =>
            resolve({ ok: true, status: 200, json: () => Promise.resolve({ recipients: 1 }) });
        })
    );

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
    is_curator: true,
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
        : Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(OWNED_WITH_GUESTS) })
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
      await screen.findByText('Too many requests. Please slow down and try again later.')
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

/**
 * Four ways this page can fail to open, and the reader does something different
 * with each: a 403 is "your access changed, go and check", a 404 is "this URL
 * is wrong", a 500 is "not your fault, try later", and a dead connection is
 * "you are offline". Only the 404 had ever been rendered by the suite, so three
 * of the four could have collapsed into any other and nothing would have said
 * so — least of all to the member who was quietly removed from a group and
 * would read "not found" as a typo.
 */
describe('the ways a collection fails to load', () => {
  const renderAfter = (response) => {
    apiFetch.mockImplementation(() => Promise.resolve(response));
    return render(
      <MemoryRouter initialEntries={['/collections/COL001']}>
        <Routes>
          <Route path="/collections/:code" element={<CollectionPage />} />
        </Routes>
      </MemoryRouter>
    );
  };

  const refused = (status) => ({ ok: false, status, json: () => Promise.resolve({}) });

  test('access you no longer have says so, and where to look', async () => {
    renderAfter(refused(403));

    expect(await screen.findByText(/your access may have changed/i)).toBeInTheDocument();
  });

  test('a collection that is not there says only that', async () => {
    renderAfter(refused(404));

    expect(await screen.findByText('Collection not found.')).toBeInTheDocument();
  });

  test('a server fault is not dressed up as a permission problem', async () => {
    renderAfter(refused(500));

    expect(await screen.findByText('Error loading collection.')).toBeInTheDocument();
    expect(screen.queryByText(/your access may have changed/i)).toBeNull();
  });

  test('being offline says so rather than blaming the collection', async () => {
    apiFetch.mockImplementation(() => Promise.reject(new Error('network down')));
    render(
      <MemoryRouter initialEntries={['/collections/COL001']}>
        <Routes>
          <Route path="/collections/:code" element={<CollectionPage />} />
        </Routes>
      </MemoryRouter>
    );

    expect(await screen.findByText('Connection error.')).toBeInTheDocument();
  });
});

describe('a join that does not take', () => {
  /* The happy path is covered above. These are the three ways it can fail, and
     they matter because the page deliberately re-fetches instead of flipping
     `is_member` locally: a visitor who is told nothing, or shown the member
     controls anyway, would go on to act on a group they never joined and meet a
     403 from an API that is right. */
  beforeEach(() => {
    localStorage.setItem('userCode', 'VISITOR1');
  });

  const renderPublic = () =>
    render(
      <MemoryRouter initialEntries={['/collections/COL001']}>
        <Routes>
          <Route path="/collections/:code" element={<CollectionPage />} />
        </Routes>
      </MemoryRouter>
    );

  const page = () =>
    Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(PUBLIC_COMMUNITY) });

  async function pressJoin() {
    renderPublic();
    fireEvent.click(await screen.findByRole('button', { name: 'Join this group' }));
  }

  test('a refused join says so and leaves the door where it was', async () => {
    apiFetch.mockImplementation((url, options) =>
      options?.method === 'POST'
        ? Promise.resolve({ ok: false, status: 403, json: () => Promise.resolve({}) })
        : page()
    );

    await pressJoin();

    expect(await screen.findByRole('alert')).toHaveTextContent(/couldn't add you to the group/i);
    expect(screen.getByRole('button', { name: 'Join this group' })).toBeInTheDocument();
  });

  test('a join whose re-fetch fails is not reported as a success', async () => {
    // The subtle one: the server did add them, but the page cannot prove what
    // that changed. Claiming membership on a payload it never received is how a
    // page ends up showing controls the API will refuse.
    let getCalls = 0;
    apiFetch.mockImplementation((url, options) => {
      if (options?.method === 'POST') {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) });
      }
      getCalls += 1;
      return getCalls === 1
        ? page()
        : Promise.resolve({ ok: false, status: 500, json: () => Promise.resolve({}) });
    });

    await pressJoin();

    expect(await screen.findByRole('alert')).toHaveTextContent(/couldn't add you to the group/i);
  });

  test('a connection lost mid-join says so too', async () => {
    apiFetch.mockImplementation((url, options) =>
      options?.method === 'POST' ? Promise.reject(new Error('network down')) : page()
    );

    await pressJoin();

    expect(await screen.findByRole('alert')).toHaveTextContent(/couldn't add you to the group/i);
  });
});

// ════════════════════════════════════════════════════════════════════════
// A COMMUNITY member's own notifications and own INACTIVE thing — both used
// to be gated on `isOwner` (the *collection* owner), which only happened to
// be right in PROPRIETARY mode, where that person and the thing's owner are
// the same. In COMMUNITY mode a member owns what they contributed, and
// stayed stranded: their own hold request never reached them here, and a
// completed/hidden thing of theirs was reachable nowhere on this page.
// ════════════════════════════════════════════════════════════════════════
describe("CollectionPage — a COMMUNITY member's own things and notifications", () => {
  const MY_INACTIVE_THING = {
    code: 'THG002',
    headline: 'My contributed gift',
    type: 'GIFT_THING',
    status: 'INACTIVE',
    owner: 'ABC123', // the signed-in viewer (localStorage userCode), not the collection owner
    owner_name: 'Me',
    created: '2026-07-01T10:00:00Z',
    tags: [],
    gallery_urls: [],
  };
  const MEMBER_COMMUNITY = {
    ...COLLECTION_WITH_PHOTO,
    thumbnail_url: '',
    mode: 'COMMUNITY',
    owner: 'OTHER1',
    owner_name: 'The Curator',
    is_member: true,
    // The viewer here is a plain member of somebody else's group, not a
    // curator — override rather than inherit COLLECTION_WITH_PHOTO's true.
    is_curator: false,
    things: [MY_INACTIVE_THING],
  };

  test('a member sees the "Inactive things" section for their own INACTIVE contribution', async () => {
    apiFetch.mockImplementation((url) => {
      if (url.startsWith('/api/v1/inbox/')) {
        return Promise.resolve({ ok: true, status: 200, json: async () => [] });
      }
      return Promise.resolve({ ok: true, status: 200, json: async () => MEMBER_COMMUNITY });
    });

    render(
      <MemoryRouter initialEntries={['/collections/COL001']}>
        <Routes>
          <Route path="/collections/:code" element={<CollectionPage />} />
        </Routes>
      </MemoryRouter>
    );

    await screen.findByRole('heading', { name: 'Inactive things' });
    expect(screen.getByText('My contributed gift')).toBeInTheDocument();
    // The per-card owner-button-matrix (isOwner keyed on the *thing*'s owner)
    // was already right — it is the section wrapping it that used to be hidden.
    expect(screen.getByRole('link', { name: 'Edit' })).toBeInTheDocument();
  });

  test('a co-member who does not own the thing still does not see the section', async () => {
    // Not a general "INACTIVE things are visible in COMMUNITY" change — only an
    // exception for the thing's own owner. The backend enforces this; here we
    // just confirm the frontend gate doesn't invent visibility of its own by
    // rendering a section the payload never carries a member's own thing in.
    const collectionWithSomeoneElsesInactiveThing = {
      ...MEMBER_COMMUNITY,
      things: [], // the backend already excluded it for this viewer
    };
    apiFetch.mockImplementation((url) => {
      if (url.startsWith('/api/v1/inbox/')) {
        return Promise.resolve({ ok: true, status: 200, json: async () => [] });
      }
      return Promise.resolve({
        ok: true,
        status: 200,
        json: async () => collectionWithSomeoneElsesInactiveThing,
      });
    });

    render(
      <MemoryRouter initialEntries={['/collections/COL001']}>
        <Routes>
          <Route path="/collections/:code" element={<CollectionPage />} />
        </Routes>
      </MemoryRouter>
    );

    await screen.findByText('Kitchen Collection');
    expect(screen.queryByRole('heading', { name: 'Inactive things' })).toBeNull();
  });

  test('a member (not the collection owner) sees a hold request on their own thing here', async () => {
    const notification = {
      code: 'NOT001',
      type: 'BOOKING_REQUESTED',
      payload: {
        thing_headline: 'My contributed gift',
        requester_name: 'Someone Else',
        booking_code: 'BOK001',
        thing_code: 'THG002',
        collection_code: 'COL001',
      },
      created: '2026-09-04T10:00:00Z',
    };
    apiFetch.mockImplementation((url) => {
      if (url.startsWith('/api/v1/inbox/')) {
        // Proof this is the collection-scoped call, not the unscoped Home one.
        expect(url).toBe('/api/v1/inbox/?collection=COL001');
        return Promise.resolve({ ok: true, status: 200, json: async () => [notification] });
      }
      return Promise.resolve({
        ok: true,
        status: 200,
        json: async () => ({ ...MEMBER_COMMUNITY, things: [] }),
      });
    });

    render(
      <MemoryRouter initialEntries={['/collections/COL001']}>
        <Routes>
          <Route path="/collections/:code" element={<CollectionPage />} />
        </Routes>
      </MemoryRouter>
    );

    expect(await screen.findByText('New hold request')).toBeInTheDocument();
    expect(screen.getByText('Someone Else requested My contributed gift.')).toBeInTheDocument();
  });

  test('a signed-out visitor on a PUBLIC collection triggers no inbox call at all', async () => {
    localStorage.clear(); // no userCode: neither isOwner nor is_member can be true
    apiFetch.mockImplementation(() =>
      Promise.resolve({
        ok: true,
        status: 200,
        json: async () => ({ ...MEMBER_COMMUNITY, is_member: false, visibility: 'PUBLIC' }),
      })
    );

    render(
      <MemoryRouter initialEntries={['/collections/COL001']}>
        <Routes>
          <Route path="/collections/:code" element={<CollectionPage />} />
        </Routes>
      </MemoryRouter>
    );

    await screen.findByText('Kitchen Collection');
    expect(apiFetch.mock.calls.some(([u]) => u.startsWith('/api/v1/inbox/'))).toBe(false);
  });
});

describe('CollectionPage as a co-owner', () => {
  // A co-owner is not the founder (`owner`), but the server says `is_curator:
  // true` — that field, not the client-side owner comparison, is what now
  // unlocks every admin control on this page.
  const CO_OWNED = {
    code: 'COL001',
    headline: 'Kitchen Collection',
    description: 'Things from the kitchen',
    status: 'ACTIVE',
    visibility: 'PRIVATE',
    mode: 'COMMUNITY',
    owner: 'OTHER1',
    owner_name: 'The Founder',
    is_curator: true,
    is_member: false,
    co_owners: [{ code: 'ABC123', name: 'Me' }],
    thumbnail_url: '',
    tags: [],
    things: [],
    invites: [{ code: 'ABC123', name: 'Me' }],
    is_paused: false,
    allowed_thing_types: [],
    digest_frequency: 'WEEKLY',
    is_digest_muted: false,
    allow_member_proposals: false,
  };

  test('sees the same admin controls the founder would, not the "join" nudge', async () => {
    apiFetch.mockImplementation((url) =>
      url.startsWith('/api/v1/inbox/')
        ? Promise.resolve({ ok: true, status: 200, json: async () => [] })
        : Promise.resolve({ ok: true, status: 200, json: async () => CO_OWNED })
    );

    render(
      <MemoryRouter initialEntries={['/collections/COL001']}>
        <Routes>
          <Route path="/collections/:code" element={<CollectionPage />} />
        </Routes>
      </MemoryRouter>
    );

    expect(await screen.findByRole('link', { name: 'Edit collection' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Manage guests' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Join this group' })).not.toBeInTheDocument();
  });

  test('the hero names the whole team on one "Co-curators:" line, founder first', async () => {
    apiFetch.mockImplementation((url) =>
      url.startsWith('/api/v1/inbox/')
        ? Promise.resolve({ ok: true, status: 200, json: async () => [] })
        : Promise.resolve({
            ok: true,
            status: 200,
            json: async () => ({
              ...CO_OWNED,
              co_owners: [
                { code: 'ABC123', name: 'Me' },
                { code: 'XYZ999', name: 'Nil' },
              ],
            }),
          })
    );

    render(
      <MemoryRouter initialEntries={['/collections/COL001']}>
        <Routes>
          <Route path="/collections/:code" element={<CollectionPage />} />
        </Routes>
      </MemoryRouter>
    );

    const line = (await screen.findByText(/Co-curators:/)).closest('p');
    // founder first, then each co-curator, all linked
    expect(line).toHaveTextContent('Co-curators: The Founder, Me, Nil');
    expect(within(line).getByRole('link', { name: 'The Founder' })).toHaveAttribute(
      'href',
      '/OTHER1'
    );
    expect(within(line).getByRole('link', { name: 'Nil' })).toHaveAttribute('href', '/XYZ999');
    // the separate single-owner line is gone
    expect(screen.queryByText('Curator:')).not.toBeInTheDocument();
  });

  test('with no co-curators the hero shows the single "Curator:" line (non-owner viewer)', async () => {
    apiFetch.mockImplementation((url) =>
      url.startsWith('/api/v1/inbox/')
        ? Promise.resolve({ ok: true, status: 200, json: async () => [] })
        : Promise.resolve({
            ok: true,
            status: 200,
            json: async () => ({ ...CO_OWNED, co_owners: [], is_curator: false, is_member: true }),
          })
    );

    render(
      <MemoryRouter initialEntries={['/collections/COL001']}>
        <Routes>
          <Route path="/collections/:code" element={<CollectionPage />} />
        </Routes>
      </MemoryRouter>
    );

    const line = (await screen.findByText(/Curator:/)).closest('p');
    expect(line).toHaveTextContent('Curator: The Founder');
    expect(screen.queryByText(/Co-curators:/)).not.toBeInTheDocument();
  });
});

/**
 * The hero's back link always SAYS "← Home" (CA, 2026-09-21), whatever it points
 * at: the group's own `Collection.home_page` when the owner has set one, the
 * app's home otherwise. It used to say "The group's site" and carry an
 * external-link icon; the wording and the icon are gone, the destination stayed.
 *
 * The label is asserted through the raw i18n key as well as the visible name —
 * the string that named the destination was deleted, so a resurrected
 * `t('collectionPage.backToSite')` would render its own key, which a name query
 * for "site" would never match. And the link carries exactly one icon (the
 * arrow): a second one is the external-link icon coming back.
 */
describe('CollectionPage back link says Home wherever it goes', () => {
  const renderPage = () =>
    render(
      <MemoryRouter initialEntries={['/collections/COL001']}>
        <Routes>
          <Route path="/collections/:code" element={<CollectionPage />} />
        </Routes>
      </MemoryRouter>
    );

  const mockCollection = (extra) =>
    apiFetch.mockImplementation((url) =>
      url.startsWith('/api/v1/inbox/')
        ? Promise.resolve({ ok: true, status: 200, json: async () => [] })
        : Promise.resolve({
            ok: true,
            status: 200,
            json: async () => ({ ...COLLECTION_WITH_PHOTO, thumbnail_url: '', ...extra }),
          })
    );

  test.each([
    ['no home_page', {}, '/', false],
    [
      'an https home_page',
      { home_page: 'https://ateneu.example/' },
      'https://ateneu.example/',
      true,
    ],
    // The backend URLField would let ftp:// through; `sanitizeUrl` here does not.
    ['a non-http home_page', { home_page: 'ftp://ateneu.example/' }, '/', false],
  ])(
    'with %s, the link says Home and goes where it should',
    async (_case, extra, href, external) => {
      mockCollection(extra);
      const { container } = renderPage();

      const back = await screen.findByRole('link', { name: /Home/ });
      expect(back).toHaveAttribute('href', href);
      expect(back).toHaveClass('back-link');
      // Only the external variant is a plain anchor that leaves the app.
      if (external) expect(back).toHaveAttribute('rel', 'noopener noreferrer');
      else expect(back).not.toHaveAttribute('rel');
      expect(back.querySelectorAll('svg')).toHaveLength(1);
      expect(container.textContent).not.toMatch(/collectionPage\.backToSite/);
    }
  );
});

/**
 * A collection's own language used to override the owner's own translations
 * for every reader without a saved preference — every anonymous visitor
 * among them — because owner text resolves by the reader's current language
 * and the override changed it. Pinned end to end on the headline a stranger
 * sees first (the hook's own rule is in useCollectionLanguage.test.jsx).
 */
describe('CollectionPage — the owner wrote in the visitor’s language', () => {
  const renderAnon = (collection) => {
    localStorage.clear();
    apiFetch.mockImplementation(() =>
      Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(collection) })
    );
    return render(
      <MemoryRouter initialEntries={['/collections/COL001']}>
        <Routes>
          <Route path="/collections/:code" element={<CollectionPage />} />
        </Routes>
      </MemoryRouter>
    );
  };

  afterEach(async () => {
    const { default: i18n } = await import('../i18n');
    await i18n.changeLanguage('en');
    localStorage.removeItem('i18nextLng');
  });

  test('a visitor reads the translation the owner wrote for them', async () => {
    renderAnon({
      ...PUBLIC_COMMUNITY,
      language: 'ca',
      headline: '{"ca": "Eines del barri", "en": "Neighbourhood tools"}',
    });

    expect(
      await screen.findByRole('heading', { level: 1, name: /Neighbourhood tools/ })
    ).toBeInTheDocument();
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(screen.queryByText(/Eines del barri/)).not.toBeInTheDocument();
  });

  test('with no translation for them, the collection’s language still applies', async () => {
    // The same page with the override free to act — what makes the test above
    // a claim about the veto and not about a harness that never switches.
    renderAnon({
      ...PUBLIC_COMMUNITY,
      language: 'ca',
      headline: '{"ca": "Eines del barri", "es": "Herramientas del barrio"}',
    });

    expect(
      await screen.findByRole('heading', { level: 1, name: /Eines del barri/ })
    ).toBeInTheDocument();
  });
});

/**
 * A group's welcome PDF reached a member once, in the email sent when they
 * joined, and nowhere else: a member who had deleted it could not find it
 * again. The API serves `welcome_doc_url` to curators and members only (the
 * 2026-09-18 security round), so the page shows whatever it is given.
 */
describe('CollectionPage — the welcome document', () => {
  const renderWith = (collection) => {
    apiFetch.mockImplementation(() =>
      Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(collection) })
    );
    return render(
      <MemoryRouter initialEntries={['/collections/COL001']}>
        <Routes>
          <Route path="/collections/:code" element={<CollectionPage />} />
        </Routes>
      </MemoryRouter>
    );
  };

  test('a member can open it from the group page, in a new tab', async () => {
    renderWith({
      ...PUBLIC_COMMUNITY,
      is_member: true,
      welcome_doc_url: 'https://bucket.example.com/oiueei/documents/welcome.pdf',
    });

    const link = await screen.findByRole('link', { name: /welcome document \(PDF\)/ });
    expect(link).toHaveAttribute('href', 'https://bucket.example.com/oiueei/documents/welcome.pdf');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', expect.stringContaining('noopener'));
  });

  test('no document, or none served to this reader, means no link', async () => {
    renderWith({ ...PUBLIC_COMMUNITY, welcome_doc_url: '' });

    await screen.findByRole('heading', { level: 1 });
    expect(screen.queryByRole('link', { name: /welcome document/ })).not.toBeInTheDocument();
  });
});

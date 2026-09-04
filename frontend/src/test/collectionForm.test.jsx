import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router';
import { vi, describe, test, expect, beforeEach } from 'vitest';

window.scrollTo = vi.fn();

vi.mock('../services/api', () => ({
  apiFetch: vi.fn(() =>
    Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) })
  ),
  extractApiError: vi.fn(() => Promise.resolve('')),
  getCsrfToken: vi.fn(() => 'mock-csrf'),
}));

import { apiFetch } from '../services/api';
import CreateCollectionPage from '../pages/CreateCollectionPage';
import EditCollectionPage from '../pages/EditCollectionPage';

function mockResponse(data, ok = true) {
  return { ok, status: ok ? 200 : 400, json: () => Promise.resolve(data) };
}

// `collection` feeds EditCollectionPage's load fetch; Create POSTs, Edit PATCHes.
function setApi({ collection = {} } = {}) {
  apiFetch.mockImplementation((url, opts = {}) => {
    const method = opts.method || 'GET';
    if (url === '/api/v1/collections/' && method === 'POST')
      return Promise.resolve(mockResponse({ code: 'NEW001' }));
    if (/\/collections\/[^/]+\//.test(url)) return Promise.resolve(mockResponse(collection));
    return Promise.resolve(mockResponse({}));
  });
}

function renderCreate() {
  setApi();
  return render(
    <MemoryRouter initialEntries={['/collections/new']}>
      <Routes>
        <Route path="/collections/new" element={<CreateCollectionPage />} />
        <Route path="*" element={<div data-testid="navigated" />} />
      </Routes>
    </MemoryRouter>
  );
}

function renderEdit(collection) {
  setApi({ collection });
  return render(
    <MemoryRouter initialEntries={['/collections/COL001/edit']}>
      <Routes>
        <Route path="/collections/:code/edit" element={<EditCollectionPage />} />
        <Route path="*" element={<div data-testid="navigated" />} />
      </Routes>
    </MemoryRouter>
  );
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
  setApi();
});

// ════════════════════════════════════════════════════════════════════════
// CreateCollectionPage — mode-gated toggles + submit
// ════════════════════════════════════════════════════════════════════════
describe('CreateCollectionPage', () => {
  test('PROPRIETARY (default): no album-mode toggle', () => {
    renderCreate();

    expect(screen.queryByRole('button', { name: /Album mode/ })).toBeNull();
  });

  // P1-5: the mode picker is a radio group with an inline description per option,
  // not a Select hidden behind an info icon.
  test('mode radios render with inline descriptions', () => {
    renderCreate();

    expect(screen.getByRole('radio', { name: 'Proprietary' })).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: 'Community' })).toBeInTheDocument();
    expect(screen.getByText('Only you can add things to this list.')).toBeInTheDocument();
    expect(
      screen.getByText('Everyone you invite can add their own things too.')
    ).toBeInTheDocument();
  });

  // The mode radio's one surviving side effect. It used to reveal the swap and
  // share toggles as well; those types were extirpated this release, and the
  // test that carried their name was left clicking the radio and asserting
  // nothing at all — green no matter what the radio did. What the radio still
  // decides is the group's visibility default: a community is born public so a
  // stranger can reach it, a proprietary list private. Backwards, that either
  // hides a community from the whole funnel or publishes a private list.
  test('choosing Community makes the new group public, and Proprietary private again', () => {
    const { container } = renderCreate();
    const visibility = () => container.querySelector('#create-collection-visibility');

    expect(visibility()).toHaveAttribute('aria-pressed', 'false');

    fireEvent.click(screen.getByRole('radio', { name: 'Community' }));
    expect(visibility()).toHaveAttribute('aria-pressed', 'true');

    fireEvent.click(screen.getByRole('radio', { name: 'Proprietary' }));
    expect(visibility()).toHaveAttribute('aria-pressed', 'false');
  });

  // It is a default, not a lock — "the owner can still flip the toggle
  // afterwards". Which is only true if the flip survives to the POST.
  test('the owner can overrule the mode default, and their choice is what ships', async () => {
    const { container } = renderCreate();
    await fillTheRequiredFields(container, 'A quiet community');

    fireEvent.click(screen.getByRole('radio', { name: 'Community' }));
    fireEvent.click(container.querySelector('#create-collection-visibility'));
    fireEvent.click(screen.getByRole('button', { name: 'Create' }));

    await waitFor(() => expect(createBody()?.visibility).toBe('PRIVATE'));
    expect(createBody()?.mode).toBe('COMMUNITY');
  });

  // O1: the optional fields (thumbnail, welcome doc, tags, language, rental rules)
  // fold into a "More options" accordion, closed on load, so the happy path is
  // just title + mode + who-can-add. Nothing inside it is required or can block
  // submit, so the form is still completable without ever opening it.
  test('optional fields stay hidden until "More options" is opened', async () => {
    const { container } = renderCreate();

    const thumb = () => container.querySelector('#create-collection-thumbnail');
    expect(thumb()).not.toBeVisible();
    expect(container.querySelector('#create-collection-welcome-doc')).not.toBeVisible();

    fireEvent.click(screen.getByRole('button', { name: 'More options' }));

    await waitFor(() => expect(thumb()).toBeVisible());
    expect(container.querySelector('#create-collection-welcome-doc')).toBeVisible();
  });

  // The Create form used to omit the digest field entirely. That was survivable
  // while `digest_frequency` defaulted to NONE; it stopped being survivable when
  // the default became WEEKLY, because a group now mails its members from the
  // moment it exists. The owner has to see — and be able to change — that at the
  // moment they create it, which is exactly what these two pin.
  test('the digest field is on the Create form, folded into "More options"', async () => {
    const { container } = renderCreate();

    const digest = () => container.querySelector('#create-collection-digest');
    expect(digest()).not.toBeVisible();

    fireEvent.click(screen.getByRole('button', { name: 'More options' }));

    await waitFor(() => expect(digest()).toBeVisible());
  });

  // "Pick at least one type" is the only thing besides the headline that can
  // block submit, so this is the shortest path to a valid Create.
  async function fillTheRequiredFields(container, headline) {
    fireEvent.change(container.querySelector('#create-collection-headline'), {
      target: { value: headline },
    });
    fireEvent.click(container.querySelector('#create-collection-allowed-thing-types-main-button'));
    fireEvent.click(await screen.findByRole('option', { name: 'Gift' }));
  }

  const createBody = () => {
    const post = apiFetch.mock.calls.find(
      ([u, o]) => u === '/api/v1/collections/' && o?.method === 'POST'
    );
    return post && JSON.parse(post[1].body);
  };

  test('a new collection is created subscribed to its own digest', async () => {
    const { container } = renderCreate();
    await fillTheRequiredFields(container, 'The street');

    fireEvent.click(screen.getByRole('button', { name: 'Create' }));

    // Not "whatever the server defaults to": the value the owner was shown in
    // the form is the value that ships, so the field can never disagree with
    // the row it created.
    await waitFor(() => expect(createBody()?.digest_frequency).toBe('WEEKLY'));
  });

  test('turning the digest off at creation time is honoured', async () => {
    const { container } = renderCreate();
    await fillTheRequiredFields(container, 'Quiet group');

    fireEvent.click(screen.getByRole('button', { name: 'More options' }));
    fireEvent.click(await screen.findByRole('combobox', { name: /Digest emails/ }));
    fireEvent.click(await screen.findByRole('option', { name: 'None' }));
    fireEvent.click(screen.getByRole('button', { name: 'Create' }));

    await waitFor(() => expect(createBody()?.digest_frequency).toBe('NONE'));
  });

  // The toggle that decides whether members may recommend guests at all: the
  // owner's answer to "am I willing to be asked", which a group with a waiting
  // list or an admission process may not be. It has to reach the POST.
  test('the recommend-a-guest setting reaches the create request', async () => {
    const { container } = renderCreate();
    await fillTheRequiredFields(container, 'Closed group');

    fireEvent.click(container.querySelector('#create-collection-allow-proposals'));
    fireEvent.click(screen.getByRole('button', { name: 'Create' }));

    await waitFor(() => expect(createBody()?.allow_member_proposals).toBe(false));
  });

  test('left alone, a group is willing to be asked', async () => {
    const { container } = renderCreate();
    await fillTheRequiredFields(container, 'Open group');

    fireEvent.click(screen.getByRole('button', { name: 'Create' }));

    await waitFor(() => expect(createBody()?.allow_member_proposals).toBe(true));
  });
});

describe('EditCollectionPage — load + pause + submit', () => {
  test('pre-populates the headline from the loaded collection', async () => {
    renderEdit({
      headline: 'Loaded Name',
      mode: 'PROPRIETARY',
      allowed_thing_types: ['GIFT_THING'],
    });

    expect(await screen.findByDisplayValue('Loaded Name')).toBeInTheDocument();
  });

  test('pause section shows the message field + "Pause collection" when not paused', async () => {
    const { container } = renderEdit({
      headline: 'Comm',
      mode: 'PROPRIETARY',
      allowed_thing_types: ['GIFT_THING'],
      is_paused: false,
    });

    await screen.findByDisplayValue('Comm');
    expect(container.querySelector('#pause-message')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Pause collection' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Resume collection' })).toBeNull();
  });

  test('pause section shows the message + "Resume collection" when paused', async () => {
    const { container } = renderEdit({
      headline: 'Comm',
      mode: 'PROPRIETARY',
      allowed_thing_types: ['GIFT_THING'],
      is_paused: true,
      pause_message: 'Back in a week',
    });

    await screen.findByDisplayValue('Comm');
    expect(container.querySelector('#pause-message')).toBeNull();
    expect(screen.getByText('Back in a week')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Resume collection' })).toBeInTheDocument();
  });

  // O1 on Edit: digest, language, thumbnail and the welcome doc fold into the
  // same "More options" accordion; status, mode and the identity cluster stay
  // visible. The digest select lives on BOTH forms now (see the Create suite
  // above) — it is folded here, not exclusive to here.
  test('the digest select is hidden until "More options" is opened', async () => {
    const { container } = renderEdit({
      headline: 'Comm',
      mode: 'PROPRIETARY',
      allowed_thing_types: ['GIFT_THING'],
    });

    await screen.findByDisplayValue('Comm');
    const digest = () => container.querySelector('#edit-collection-digest');
    expect(digest()).not.toBeVisible();

    fireEvent.click(screen.getByRole('button', { name: 'More options' }));

    await waitFor(() => expect(digest()).toBeVisible());
  });

  test('PATCHes /api/v1/collections/{code}/ with the edited fields', async () => {
    const { container } = renderEdit({
      headline: 'Old Name',
      mode: 'PROPRIETARY',
      allowed_thing_types: ['GIFT_THING'],
    });

    await screen.findByDisplayValue('Old Name');
    fireEvent.change(container.querySelector('#edit-collection-headline'), {
      target: { value: 'New Name' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => {
      const call = apiFetch.mock.calls.find(
        (c) =>
          c[0] === '/api/v1/collections/COL001/' &&
          c[1]?.method === 'PATCH' &&
          JSON.parse(c[1].body).headline !== undefined
      );
      expect(call).toBeTruthy();
      const body = JSON.parse(call[1].body);
      expect(body).toMatchObject({ headline: 'New Name', mode: 'PROPRIETARY' });
    });
  });
});

// ════════════════════════════════════════════════════════════════════════
// CollectionForm — the allowed-types select respects the deployment policy
//
// A narrowed deployment (e.g. HostedCreatorPolicy: GIFT/SELL open, LEND/RENT
// wait for approval) must not let an unvetted account choose a withheld type
// for its own collection — that config would only ever be refused later, at
// AddThingPage or the create-thing endpoint, with no explanation of why. Bug:
// this select used to ignore `capabilities` entirely, unlike the mode radios
// right above it in the same form (see CollectionModeField).
// ════════════════════════════════════════════════════════════════════════
describe('CollectionForm — thing_types capability narrows the allowed-types select', () => {
  function setApiWithCapabilities(capabilities) {
    apiFetch.mockImplementation((url, opts = {}) => {
      const method = opts.method || 'GET';
      if (url === '/api/v1/auth/me/') return Promise.resolve(mockResponse({ capabilities }));
      if (url === '/api/v1/collections/' && method === 'POST')
        return Promise.resolve(mockResponse({ code: 'NEW001' }));
      return Promise.resolve(mockResponse({}));
    });
  }

  test('a withheld type is left off the select, with the approval notice underneath', async () => {
    // The hook caches one request per signed-in account, so a code no other
    // test in this file uses keeps this answer from being served stale.
    localStorage.setItem('userCode', 'POPIN01');
    setApiWithCapabilities({
      collection_modes: ['PROPRIETARY', 'COMMUNITY'],
      thing_types: ['GIFT_THING', 'SELL_THING'],
      request_url: 'https://example.test/request-access/',
    });

    const { container } = render(
      <MemoryRouter initialEntries={['/collections/new']}>
        <Routes>
          <Route path="/collections/new" element={<CreateCollectionPage />} />
          <Route path="*" element={<div data-testid="navigated" />} />
        </Routes>
      </MemoryRouter>
    );

    fireEvent.click(container.querySelector('#create-collection-allowed-thing-types-main-button'));
    expect(await screen.findByRole('option', { name: 'Gift' })).toBeInTheDocument();
    expect(screen.queryByRole('option', { name: 'Rental' })).toBeNull();
    expect(screen.queryByRole('option', { name: 'Lend' })).toBeNull();

    expect(
      await screen.findByText('Some options need approval on this deployment: Rental, Lend.')
    ).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Request access/ })).toHaveAttribute(
      'href',
      'https://example.test/request-access/'
    );
  });

  test('a type already on the collection stays offered even if the policy no longer allows it', async () => {
    // Mirrors the server, which only judges a *change* — Edit must not hide
    // (and silently drop, on the next save) a type the collection already has.
    localStorage.setItem('userCode', 'POPIN02');
    apiFetch.mockImplementation((url) => {
      if (url === '/api/v1/auth/me/')
        return Promise.resolve(
          mockResponse({
            capabilities: {
              collection_modes: ['PROPRIETARY', 'COMMUNITY'],
              thing_types: ['GIFT_THING', 'SELL_THING'],
              request_url: 'https://example.test/request-access/',
            },
          })
        );
      if (/\/collections\/[^/]+\//.test(url))
        return Promise.resolve(
          mockResponse({
            headline: 'Grandfathered',
            mode: 'PROPRIETARY',
            allowed_thing_types: ['GIFT_THING', 'LEND_THING'],
          })
        );
      return Promise.resolve(mockResponse({}));
    });

    render(
      <MemoryRouter initialEntries={['/collections/COL001/edit']}>
        <Routes>
          <Route path="/collections/:code/edit" element={<EditCollectionPage />} />
        </Routes>
      </MemoryRouter>
    );

    await screen.findByDisplayValue('Grandfathered');
    // Already selected, so it renders as a chip rather than a menu option —
    // present at all is what this test is pinning (HDS renders the chip text
    // twice — dropdown summary + assistive copy — hence findAllByText).
    expect((await screen.findAllByText('Lend')).length).toBeGreaterThan(0);
  });
});

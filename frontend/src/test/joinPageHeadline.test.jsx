import { render, screen, waitFor, fireEvent, act } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router';
import { vi, describe, test, expect, beforeEach, afterEach } from 'vitest';

vi.mock('../services/api', () => ({
  apiFetch: vi.fn(),
  getCsrfToken: () => 'tok',
}));

import i18n from 'i18next';
import { apiFetch } from '../services/api';
import JoinPage from '../pages/JoinPage';

// JoinPage is where an anonymous visitor is asked for their email — the first
// screen of the viral funnel. It used to take the collection's name only from
// navigation state, which just one caller passes (ThingLinkbox). ThingPage's
// reserve button, a refresh and a shared /join URL all arrived with
// nothing, so the page asked a stranger to join "Collection".
function renderJoin(state, search = '') {
  return render(
    <MemoryRouter initialEntries={[{ pathname: '/collections/PUB001/join', search, state }]}>
      <Routes>
        <Route path="/collections/:code/join" element={<JoinPage />} />
      </Routes>
    </MemoryRouter>
  );
}

describe('JoinPage — the collection is named', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
  });
  afterEach(() => vi.restoreAllMocks());

  test('names the collection when arriving cold, with no navigation state', async () => {
    apiFetch.mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({
          code: 'PUB001',
          headline: 'Tool Library',
          mode: 'PROPRIETARY',
          allowed_thing_types: ['LEND_THING'],
        }),
    });

    renderJoin(undefined);

    // The named variant of the body copy — the sentence that asks for the email —
    // with the verbs the collection endpoint gave: a lending library says "borrow",
    // not the four verbs every collection used to promise.
    expect(await screen.findByText(/^Join to borrow in Tool Library\./)).toBeInTheDocument();
    expect(apiFetch).toHaveBeenCalledWith('/api/v1/collections/PUB001/', expect.anything());
  });

  test('resolves a headline written once per language into the reader own language', async () => {
    apiFetch.mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({
          code: 'PUB001',
          headline: JSON.stringify({ en: 'Tool Library', es: 'Biblioteca de herramientas' }),
          mode: 'PROPRIETARY',
          allowed_thing_types: ['LEND_THING'],
        }),
    });

    renderJoin(undefined);

    // The test i18n runs in English, so the raw map must never reach the screen.
    expect(await screen.findByText(/^Join to borrow in Tool Library\./)).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/\{"en"/);
  });

  // `useCollectionLanguage` switches this page to the group's own language once the
  // collection has loaded — which is after the name arrived. The name used to be
  // resolved at that moment and kept as words, so the title stayed in the language
  // before the switch. It has to follow the page into the new one.
  test('the name follows the page into another language after it has loaded', async () => {
    i18n.addResourceBundle('ca', 'translation', { common: { done: 'Fet' } });
    apiFetch.mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({
          code: 'PUB001',
          headline: JSON.stringify({ en: 'Tool Library', ca: "Biblioteca d'eines" }),
          mode: 'PROPRIETARY',
          allowed_thing_types: ['LEND_THING'],
        }),
    });

    try {
      renderJoin(undefined);
      expect(
        await screen.findByRole('heading', { level: 1, name: 'Join Tool Library' })
      ).toBeInTheDocument();

      await act(() => i18n.changeLanguage('ca'));

      expect(
        await screen.findByRole('heading', { level: 1, name: "Join Biblioteca d'eines" })
      ).toBeInTheDocument();
    } finally {
      await act(() => i18n.changeLanguage('en'));
      i18n.removeResourceBundle('ca', 'translation');
    }
  });

  test('a collection it cannot read leaves the generic copy, not a broken name', async () => {
    apiFetch.mockResolvedValue({ ok: false, status: 404 });

    renderJoin(undefined);

    await waitFor(() => expect(apiFetch).toHaveBeenCalled());
    expect(screen.getByText(/Join to request, reserve/)).toBeInTheDocument();
  });

  test('a ?thing= from a "Reserve" click rides into the join request', async () => {
    apiFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ code: 'PUB001', headline: 'Tool Library' }),
    });
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ message: 'sent' }),
    });

    renderJoin(undefined, '?thing=THG001');

    fireEvent.change(await screen.findByLabelText(/Email/), {
      target: { value: 'visitor@example.com' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Send me a magic link' }));

    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
    const body = JSON.parse(globalThis.fetch.mock.calls[0][1].body);
    expect(body.collection_code).toBe('PUB001');
    expect(body.thing_code).toBe('THG001');
  });

  test('no ?thing= means no thing_code in the request', async () => {
    apiFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ code: 'PUB001', headline: 'Tool Library' }),
    });
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ message: 'sent' }),
    });

    renderJoin(undefined);

    fireEvent.change(await screen.findByLabelText(/Email/), {
      target: { value: 'visitor@example.com' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Send me a magic link' }));

    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
    const body = JSON.parse(globalThis.fetch.mock.calls[0][1].body);
    expect(body).not.toHaveProperty('thing_code');
  });
});

/**
 * "Join {collection}": the title says which group the stranger is
 * about to join, the way `/share/:token` already does — it used to be "Join to
 * take part" with the name only in the text below and in the way back. The words
 * are the share page's own (`share.pageTitleNamed`, `titles.shareNamed`); until
 * the name is known the title of always.
 */
describe('JoinPage — the title names the collection', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
  });
  afterEach(() => vi.restoreAllMocks());

  const collectionNamed = (headline) =>
    apiFetch.mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({
          code: 'PUB001',
          headline,
          mode: 'PROPRIETARY',
          allowed_thing_types: ['LEND_THING'],
        }),
    });

  test('with the collection loaded, the h1 and the tab both say "Join {name}"', async () => {
    collectionNamed('Tool Library');

    renderJoin(undefined);

    expect(
      await screen.findByRole('heading', { level: 1, name: 'Join Tool Library' })
    ).toBeInTheDocument();
    await waitFor(() => expect(document.title).toBe('Join Tool Library — OIUEEI'));
    expect(screen.queryByRole('heading', { level: 1, name: 'Join to take part' })).toBeNull();
  });

  test('a headline written once per language is read in the reader’s own', async () => {
    collectionNamed(JSON.stringify({ en: 'Tool Library', es: 'Biblioteca de herramientas' }));

    renderJoin(undefined);

    expect(
      await screen.findByRole('heading', { level: 1, name: 'Join Tool Library' })
    ).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/\{"en"/);
  });

  test('with the name already in the navigation state it is there from the first paint', () => {
    // The collection call never answers: nothing but the state can have named it.
    apiFetch.mockReturnValue(new Promise(() => {}));

    renderJoin({ collectionHeadline: 'Tool Library' });

    expect(
      screen.getByRole('heading', { level: 1, name: 'Join Tool Library' })
    ).toBeInTheDocument();
    expect(document.title).toBe('Join Tool Library — OIUEEI');
  });

  test('without a name — a collection it cannot read — it is the title of always', async () => {
    apiFetch.mockResolvedValue({ ok: false, status: 404 });

    renderJoin(undefined);

    await waitFor(() => expect(apiFetch).toHaveBeenCalled());
    expect(
      screen.getByRole('heading', { level: 1, name: 'Join to take part' })
    ).toBeInTheDocument();
    expect(document.title).toBe('Join to take part — OIUEEI');
  });
});

/**
 * The door looks like the page it leads to: a collection with a
 * photo paints it in the hero with the same composition its own page uses
 * (`HeroPhoto`), where `/join` used to be a plain hero in the same colours. The
 * photo comes from the collection endpoint the page already calls, which gives
 * `thumbnail_url` to an anonymous reader of a PUBLIC collection.
 */
describe('JoinPage — the hero carries the collection’s photo', () => {
  const PHOTO = 'https://bucket.example.com/oiueei/collections/cover.jpg';

  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
  });
  afterEach(() => vi.restoreAllMocks());

  const collectionWith = (thumbnail_url) =>
    apiFetch.mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({
          code: 'PUB001',
          headline: 'Tool Library',
          mode: 'PROPRIETARY',
          allowed_thing_types: ['LEND_THING'],
          thumbnail_url,
        }),
    });

  test('with a photo, the hero shows it and takes the photo layout', async () => {
    collectionWith(PHOTO);

    const { container } = renderJoin(undefined);

    const photo = await screen.findByRole('img', { name: 'Tool Library' });
    expect(photo).toHaveAttribute('src', PHOTO);
    expect(container.querySelector('.form-hero')).toHaveClass('form-hero--photo');
    // The words are still in the hero, above the photo's wedge.
    expect(
      screen.getByRole('heading', { level: 1, name: 'Join Tool Library' })
    ).toBeInTheDocument();
  });

  test('without one, the hero is the plain one: no image, no photo layout', async () => {
    collectionWith('');

    const { container } = renderJoin(undefined);

    await screen.findByText(/^Join to borrow in Tool Library\./);
    expect(screen.queryByRole('img')).not.toBeInTheDocument();
    expect(container.querySelector('.form-hero')).not.toHaveClass('form-hero--photo');
  });
});

import { render, screen, waitFor, fireEvent, act } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router';
import { describe, test, expect, vi, beforeEach, afterEach } from 'vitest';

// Only the network is faked: `extractApiError` (how a 429 reads its reason) is the real one.
vi.mock('../services/api', async () => ({
  ...(await vi.importActual('../services/api')),
  apiFetch: vi.fn(),
  getCsrfToken: vi.fn(() => 'mock-csrf'),
}));
vi.mock('../hooks/useCollectionLanguage', () => ({ default: vi.fn() }));

import { apiFetch } from '../services/api';
import useCollectionLanguage from '../hooks/useCollectionLanguage';
import SharePage from './SharePage';
import en from '../i18n/locales/en.json';

// A stand-in for the 22-char URL-safe share token; kept low-entropy so a
// secret scanner doesn't mistake the fixture for a real credential.
const TOKEN = 'demo-share-token';

function renderShare() {
  return render(
    <MemoryRouter initialEntries={[`/share/${TOKEN}`]}>
      <Routes>
        <Route path="/share/:token" element={<SharePage />} />
        <Route path="/collections/:code" element={<p>landed on collection</p>} />
      </Routes>
    </MemoryRouter>
  );
}

function preview(body, ok = true) {
  return Promise.resolve({ ok, status: ok ? 200 : 404, json: () => Promise.resolve(body) });
}

beforeEach(() => {
  apiFetch.mockReset();
  localStorage.clear();
  document.title = '';
});
afterEach(() => vi.restoreAllMocks());

/**
 * A reader who already has a session accepts the invitation with one button
 * (`POST /share/{token}/join/`) instead of typing an email and waiting for a magic
 * link they have no need of — and everyone else still gets the form. In a
 * neighbourhood the same people are in several groups and this link is the main
 * viral route, so the round trip was paid by exactly the people who use it most.
 */
describe('SharePage — a reader who is already signed in', () => {
  const JOIN = `/api/v1/share/${TOKEN}/join/`;
  const answer = (status, body) =>
    Promise.resolve({ ok: status < 400, status, json: () => Promise.resolve(body) });
  const posts = () => apiFetch.mock.calls.filter(([, options]) => options?.method === 'POST');

  /** The preview always lands; `join` decides what the POST does. */
  function serve(join) {
    apiFetch.mockImplementation((url) =>
      url === JOIN ? join() : preview({ headline: 'The Tool Library', description: '' })
    );
  }

  beforeEach(() => {
    localStorage.setItem('userCode', 'USR001');
  });

  test('sees one button that names the group, and no email field', async () => {
    serve(() => answer(200, { collection: 'COL001', joined: true }));
    renderShare();

    expect(
      await screen.findByRole('button', { name: 'Join The Tool Library' })
    ).toBeInTheDocument();
    expect(screen.queryByLabelText(/Email/)).toBeNull();
    // The intro that asks for an email would contradict the button.
    expect(screen.queryByText(/Enter your email/)).toBeNull();
    expect(screen.queryByRole('link', { name: /Already have an account/ })).toBeNull();
  });

  test('before the group is named, the button says "Join this group"', async () => {
    apiFetch.mockImplementation(() => preview({ detail: 'Not found' }, false));
    renderShare();

    expect(
      await screen.findByRole('button', { name: en.share.joinSignedInGeneric })
    ).toBeInTheDocument();
  });

  test('pressing it POSTs to this token and lands on the collection', async () => {
    serve(() => answer(200, { collection: 'COL001', joined: true }));
    renderShare();

    fireEvent.click(await screen.findByRole('button', { name: 'Join The Tool Library' }));

    expect(await screen.findByText('landed on collection')).toBeInTheDocument();
    expect(posts().map(([url]) => url)).toEqual([JOIN]);
  });

  test('two presses in the same tick ask once, and the button is disabled while it waits', async () => {
    let settle;
    serve(() => new Promise((resolve) => (settle = resolve)));
    renderShare();

    const button = await screen.findByRole('button', { name: 'Join The Tool Library' });
    // Both inside one act: neither has seen the other's state update yet, so only
    // a guard that does not depend on a re-render can stop the second.
    act(() => {
      button.click();
      button.click();
    });

    await waitFor(() => expect(posts()).toHaveLength(1));
    expect(screen.getByRole('button', { name: 'Join The Tool Library' })).toBeDisabled();
    settle(await answer(200, { collection: 'COL001', joined: true }));
  });

  test('"use another email instead" brings back the form, for a shared computer', async () => {
    serve(() => answer(200, { collection: 'COL001', joined: true }));
    renderShare();

    fireEvent.click(await screen.findByRole('button', { name: en.share.useAnotherEmail }));

    expect(await screen.findByLabelText(/Email/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Join The Tool Library' })).toBeNull();
    expect(posts()).toHaveLength(0);
  });

  test('a link that no longer works says so and asks for a new one', async () => {
    serve(() => answer(404, { detail: 'Not found.' }));
    renderShare();

    fireEvent.click(await screen.findByRole('button', { name: 'Join The Tool Library' }));

    expect(await screen.findByText(en.share.linkGone)).toBeInTheDocument();
    expect(screen.queryByText('landed on collection')).toBeNull();
  });

  test('the hourly limit, which has no body, says to wait', async () => {
    serve(() =>
      Promise.resolve({ ok: false, status: 429, json: () => Promise.reject(new Error('no body')) })
    );
    renderShare();

    fireEvent.click(await screen.findByRole('button', { name: 'Join The Tool Library' }));

    expect(await screen.findByText(en.common.tooManyAttempts)).toBeInTheDocument();
  });

  test("the operator's daily ceiling says why, in the server's own words", async () => {
    const detail = "This collection has taken today's joins. Try again tomorrow.";
    serve(() => answer(429, { detail }));
    renderShare();

    fireEvent.click(await screen.findByRole('button', { name: 'Join The Tool Library' }));

    expect(await screen.findByText(detail)).toBeInTheDocument();
  });

  test('a dropped connection is said, and the button is usable again', async () => {
    serve(() => Promise.reject(new TypeError('Failed to fetch')));
    renderShare();

    fireEvent.click(await screen.findByRole('button', { name: 'Join The Tool Library' }));

    expect(await screen.findByText(en.common.connectionError)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Join The Tool Library' })).toBeEnabled();
  });

  test('a session that ran out is apiFetch redirecting to the login: no error over it', async () => {
    // apiFetch clears the session, sends the reader to /login?next=/share/… and
    // throws. Announcing "connection error" in the moment before it navigates
    // would be false.
    serve(() => Promise.reject(new Error('Unauthorised')));
    renderShare();

    fireEvent.click(await screen.findByRole('button', { name: 'Join The Tool Library' }));

    await waitFor(() => expect(posts()).toHaveLength(1));
    expect(screen.queryByText(en.common.connectionError)).toBeNull();
    expect(screen.queryByText(en.share.linkGone)).toBeNull();
  });
});

describe('SharePage — a reader with no session', () => {
  test('gets the form as always, and never a join button', async () => {
    apiFetch.mockReturnValue(preview({ headline: 'The Tool Library', description: '' }));
    renderShare();

    expect(await screen.findByLabelText(/Email/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^Join The Tool Library$/ })).toBeNull();
    expect(screen.queryByRole('button', { name: en.share.useAnotherEmail })).toBeNull();
    expect(screen.getByRole('link', { name: /Already have an account/ })).toBeInTheDocument();
  });
});

describe('SharePage — naming the collection a /share link opens', () => {
  test('asks the preview endpoint for this token on mount', async () => {
    apiFetch.mockReturnValue(preview({ headline: 'The Tool Library', description: '' }));
    renderShare();
    await waitFor(() => expect(apiFetch).toHaveBeenCalledWith(`/api/v1/share/${TOKEN}/preview/`));
  });

  test('once it lands, the page says "Join <collection>", not "Join us on OIUEEI"', async () => {
    apiFetch.mockReturnValue(
      preview({ headline: 'The Tool Library', description: 'Borrow tools, do not buy them.' })
    );
    renderShare();

    expect(
      await screen.findByRole('heading', { name: 'Join The Tool Library', level: 1 })
    ).toBeInTheDocument();
    // The collection's own words are shown too.
    expect(screen.getByText('Borrow tools, do not buy them.')).toBeInTheDocument();
    // The generic hero title is gone.
    expect(screen.queryByRole('heading', { name: 'Join us on OIUEEI' })).toBeNull();
    await waitFor(() => expect(document.title).toBe('Join The Tool Library — OIUEEI'));
  });

  test('a localized headline is resolved to the reader’s language', async () => {
    // en.json is the test locale, so the `en` value is the one that should show.
    apiFetch.mockReturnValue(
      preview({
        headline: '{"es": "El Chalmercadillo", "ca": "El mercadet", "en": "The Swap"}',
        description: '',
      })
    );
    renderShare();

    expect(
      await screen.findByRole('heading', { name: 'Join The Swap', level: 1 })
    ).toBeInTheDocument();
  });

  test('an unknown or revoked token (404) falls back to the generic copy, no error', async () => {
    apiFetch.mockReturnValue(preview({ detail: 'Not found' }, false));
    renderShare();

    expect(
      await screen.findByRole('heading', { name: 'Join us on OIUEEI', level: 1 })
    ).toBeInTheDocument();
    // Never a visible error on this page — the join form still works.
    expect(screen.queryByText(/not found/i)).toBeNull();
    expect(screen.getByLabelText(/Email/)).toBeInTheDocument();
  });

  test('a network failure also falls back silently', async () => {
    apiFetch.mockRejectedValue(new TypeError('Failed to fetch'));
    renderShare();

    expect(
      await screen.findByRole('heading', { name: 'Join us on OIUEEI', level: 1 })
    ).toBeInTheDocument();
    expect(screen.getByLabelText(/Email/)).toBeInTheDocument();
  });

  test('a preview response missing a headline is treated as no preview', async () => {
    apiFetch.mockReturnValue(preview({ description: 'orphan description' }));
    renderShare();

    expect(
      await screen.findByRole('heading', { name: 'Join us on OIUEEI', level: 1 })
    ).toBeInTheDocument();
    expect(screen.queryByText('orphan description')).toBeNull();
  });

  test("the preview's own language reaches useCollectionLanguage", async () => {
    // This is the one join door reached before a stranger is a member of
    // anything, so the collection's own language (from SharePreviewView) is
    // the only signal there is yet — without this wire, a WhatsApp link to a
    // Catalan group showed English chrome right up until the join succeeded
    // (found in review, 2026-09-15).
    apiFetch.mockReturnValue(
      preview({ headline: 'The Tool Library', description: '', language: 'ca' })
    );
    renderShare();

    // With the texts the stranger is about to read, so a translation the owner
    // wrote in the visitor's own language can keep them in it.
    await waitFor(() =>
      expect(useCollectionLanguage).toHaveBeenLastCalledWith('ca', ['The Tool Library', ''])
    );
  });

  test('a preview missing a headline never reaches useCollectionLanguage with its language', async () => {
    // `preview` state is only set when `data.headline` is present
    // (SharePage.jsx) — a preview object that failed that check must not
    // leak a stray `language` through some other path.
    apiFetch.mockReturnValue(preview({ description: 'orphan', language: 'ca' }));
    renderShare();

    await screen.findByRole('heading', { name: 'Join us on OIUEEI', level: 1 });
    expect(useCollectionLanguage).toHaveBeenLastCalledWith(undefined, [undefined, undefined]);
  });
});

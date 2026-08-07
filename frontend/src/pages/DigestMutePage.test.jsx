import { StrictMode } from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router';
import { describe, test, expect, vi, beforeEach, afterEach } from 'vitest';
import DigestMutePage from './DigestMutePage';

// The one-click unsubscribe at the foot of every digest, and the page with the
// most to lose from being wrong: it is the way out of email we send, so it has
// to work for somebody who has forgotten they have an account — and it must not
// fire for somebody who never clicked it at all.
//
// The whole design rests on the request being a POST issued from JS. A mail
// client's link scanner or a browser prefetch loads the URL and runs no
// JavaScript, so it can never unsubscribe anyone; the same guard the booking
// accept/reject links use.

function mockFetch(response) {
  globalThis.fetch = vi.fn(() => Promise.resolve(response));
}

const ok = (body = {}) => ({ ok: true, status: 200, json: async () => body });

function renderPage({ strict = false } = {}) {
  const tree = (
    <MemoryRouter initialEntries={['/digest/mute/tok-123']}>
      <Routes>
        <Route path="/digest/mute/:token" element={<DigestMutePage />} />
      </Routes>
    </MemoryRouter>
  );
  return render(strict ? <StrictMode>{tree}</StrictMode> : tree);
}

const muteCalls = () =>
  globalThis.fetch.mock.calls.filter(([u]) => String(u).includes('/digest/mute/'));

beforeEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
});
afterEach(() => vi.restoreAllMocks());

describe('DigestMutePage', () => {
  test('unsubscribes with a POST to the token, never a GET', async () => {
    mockFetch(ok({ collection_headline: 'The street' }));
    renderPage();

    await waitFor(() => expect(muteCalls()).toHaveLength(1));
    const [url, options] = muteCalls()[0];
    expect(url).toBe('/api/v1/digest/mute/tok-123/');
    // A GET here would mean a link scanner could unsubscribe a member by
    // prefetching the mail. The verb is the guard.
    expect(options.method).toBe('POST');
  });

  test('React StrictMode does not send it twice', async () => {
    // React 19 double-invokes effects in development. The endpoint is
    // idempotent, so a second call is noise rather than damage — but it is
    // noise aimed at a member's mailbox settings, and the ref that stops it is
    // easy to lose in a refactor.
    mockFetch(ok({ collection_headline: 'The street' }));
    renderPage({ strict: true });

    await screen.findByText(/won't get summaries/);
    expect(muteCalls()).toHaveLength(1);
  });

  test('names the group it silenced, so nobody wonders which one', async () => {
    mockFetch(ok({ collection_headline: 'The street' }));
    renderPage();

    expect(await screen.findByText(/“The street”/)).toBeInTheDocument();
    // And the reassurance that this cost them nothing else: the mute is scoped
    // to one group's round-up, not to the transactional mail.
    expect(screen.getByText(/still hear about your own holds/)).toBeInTheDocument();
  });

  test('a collection written in several languages resolves to the reader’s', async () => {
    mockFetch(ok({ collection_headline: '{"es": "La calle", "en": "The street"}' }));
    renderPage();

    expect(await screen.findByText(/“The street”/)).toBeInTheDocument();
    expect(screen.queryByText(/\{"es"/)).toBeNull();
  });

  test('an unnamed group still gets a plain confirmation', async () => {
    mockFetch(ok({}));
    renderPage();

    expect(
      await screen.findByText("You won't get summaries from this group any more.")
    ).toBeInTheDocument();
  });

  test('an expired or tampered link says so instead of claiming success', async () => {
    // The failure that matters: telling somebody they are unsubscribed when
    // they are not means the next digest arrives and they have no reason to
    // trust the link again.
    mockFetch({ ok: false, status: 401, json: async () => ({}) });
    renderPage();

    expect(await screen.findByText(/invalid or has expired/)).toBeInTheDocument();
    expect(screen.queryByText(/won't get summaries/)).toBeNull();
  });

  test('a dropped connection lands on the error, not a permanent spinner', async () => {
    globalThis.fetch = vi.fn(() => Promise.reject(new Error('offline')));
    renderPage();

    expect(await screen.findByText(/invalid or has expired/)).toBeInTheDocument();
  });

  test('a way out is offered whatever happened', async () => {
    mockFetch({ ok: false, status: 401, json: async () => ({}) });
    renderPage();

    await screen.findByText(/invalid or has expired/);
    // No login is involved here, so the page owes the reader somewhere to go.
    expect(screen.getByRole('link', { name: 'Home' })).toHaveAttribute('href', '/');
  });
});

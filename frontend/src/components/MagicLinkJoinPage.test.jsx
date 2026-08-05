import { render, screen, fireEvent, act } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, test, expect, vi, afterEach, beforeEach } from 'vitest';
import MagicLinkJoinPage from './MagicLinkJoinPage';

// SharePage's real configuration — the variant that carries a share_token.
function renderShareVariant() {
  return render(
    <MemoryRouter>
      <MagicLinkJoinPage
        ns="share"
        docTitleKey="titles.share"
        titleKey="share.pageTitle"
        descriptionKey="share.pageDescription"
        extraBody={{ share_token: 'TOKEN123' }}
      />
    </MemoryRouter>
  );
}

function submitEmail(email = 'newcomer@example.com') {
  fireEvent.change(screen.getByLabelText(/Email/), { target: { value: email } });
  fireEvent.click(screen.getByRole('button', { name: 'Join' }));
}

describe('MagicLinkJoinPage (the pop-in join door)', () => {
  beforeEach(() => {
    localStorage.clear();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  test('joining sends the email, the page language, and the share token', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ message: 'Magic link sent' }),
    });
    renderShareVariant();

    submitEmail('newcomer@example.com');

    await screen.findByText(/Magic link sent! Check your inbox/);
    const [url, options] = globalThis.fetch.mock.calls[0];
    expect(url).toBe('/api/v1/auth/pop-in/');
    expect(options.method).toBe('POST');
    // `language` makes the newcomer's FIRST magic link speak the language they
    // were reading this page in; `share_token` targets the shared collection.
    expect(JSON.parse(options.body)).toEqual({
      email: 'newcomer@example.com',
      language: 'en',
      share_token: 'TOKEN123',
    });
  });

  test('success replaces the form, shows the close-tab line, and resets seenWelcome', async () => {
    // A joiner may be a brand-new user on a shared browser profile: a stale
    // seenWelcome would suppress their first-time welcome box.
    localStorage.setItem('seenWelcome', 'true');
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ message: 'Magic link sent' }),
    });
    renderShareVariant();

    submitEmail();

    await screen.findByText(/Magic link sent! Check your inbox/);
    expect(screen.getByText(/You can close this tab now/)).toBeInTheDocument();
    expect(screen.queryByLabelText(/Email/)).not.toBeInTheDocument();
    expect(localStorage.getItem('seenWelcome')).toBeNull();
  });

  test('a server failure shows a readable error, and seenWelcome is untouched', async () => {
    localStorage.setItem('seenWelcome', 'true');
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      json: async () => ({ error: 'boom' }),
    });
    renderShareVariant();

    submitEmail();

    expect(await screen.findByText('Error sending link.')).toBeInTheDocument();
    expect(screen.queryByText(/You can close this tab now/)).not.toBeInTheDocument();
    expect(localStorage.getItem('seenWelcome')).toBe('true');
  });

  test('two submits in the same tick send only one magic link', async () => {
    // Every accepted pop-in emails a magic link, so a double submit mails a
    // stranger twice. `disabled={loading}` handles the ordinary double-click —
    // React flushes discrete events synchronously, so the button is already
    // disabled by the second one. What it cannot catch is two submit events
    // dispatched before any re-render: both run the same closure, where the
    // `loading` state is still false. Only usePopIn's ref guard sees the first
    // one, which is why it is a ref and not the state.
    let resolveFirst;
    globalThis.fetch = vi.fn().mockReturnValue(
      new Promise((resolve) => {
        resolveFirst = () => resolve({ ok: true, status: 200, json: async () => ({}) });
      })
    );
    const { container } = renderShareVariant();

    fireEvent.change(screen.getByLabelText(/Email/), {
      target: { value: 'newcomer@example.com' },
    });
    const form = container.querySelector('form');
    // Dispatched directly on the form, twice, inside one act() — the button's
    // disabled attribute is bypassed, reproducing the stale-closure window.
    await act(async () => {
      const evt = () => new Event('submit', { bubbles: true, cancelable: true });
      form.dispatchEvent(evt());
      form.dispatchEvent(evt());
    });

    expect(globalThis.fetch).toHaveBeenCalledTimes(1);

    resolveFirst();
    await screen.findByText(/Magic link sent! Check your inbox/);
    expect(globalThis.fetch).toHaveBeenCalledTimes(1);
  });

  test('a rate-limited join says "wait", not "broken"', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 429,
      json: async () => ({ detail: 'Request was throttled.' }),
    });
    renderShareVariant();

    submitEmail();

    expect(
      await screen.findByText('Too many attempts — please wait a moment and try again.')
    ).toBeInTheDocument();
  });
});

describe('MagicLinkJoinPage privacy information (art. 13 at the point of collection)', () => {
  test('links to /legal on the form itself, not only from /login', () => {
    // This door mints a real account from the typed email. The privacy
    // information has to be one click away *here*, at the moment the data is
    // collected — a visitor arriving on a share link never passes /login.
    renderShareVariant();
    expect(screen.getByRole('link', { name: 'Legal notice & privacy' })).toHaveAttribute(
      'href',
      '/legal'
    );
  });

  test('the link survives the form being replaced by the success notification', () => {
    // The address is already stored by then, so the information must not
    // disappear along with the form that collected it.
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ message: 'Magic link sent' }),
    });
    renderShareVariant();

    submitEmail();

    expect(screen.getByRole('link', { name: 'Legal notice & privacy' })).toBeInTheDocument();
  });
});

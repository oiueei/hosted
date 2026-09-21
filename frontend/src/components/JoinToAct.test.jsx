import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { describe, test, expect, vi, afterEach, beforeEach } from 'vitest';
import JoinToAct from './JoinToAct';

function renderJoin() {
  return render(
    <MemoryRouter>
      <JoinToAct collectionCode="PUB001" collectionHeadline="Tool Library" />
    </MemoryRouter>
  );
}

function submitEmail(email = 'visitor@example.com') {
  fireEvent.change(screen.getByLabelText(/Email/), { target: { value: email } });
  fireEvent.click(screen.getByRole('button', { name: 'Send me a magic link' }));
}

describe('JoinToAct (login-to-act on a public collection)', () => {
  beforeEach(() => {
    localStorage.clear();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  test('joining sends the email and the collection code — never a language field', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ message: 'Magic link sent' }),
    });
    renderJoin();

    // The intro names the collection the visitor is about to join.
    expect(screen.getByText(/Tool Library/)).toBeInTheDocument();
    submitEmail('visitor@example.com');

    await screen.findByText(/We've sent you a magic link to join/);
    const [url, options] = globalThis.fetch.mock.calls[0];
    expect(url).toBe('/api/v1/auth/join/');
    // No `language` — sending the page's current UI language used to get it
    // stamped permanently onto the new member, outranking the collection's
    // own language for every email to them from then on (CA's report,
    // 2026-09-15). The backend now resolves their very first magic link from
    // the collection instead.
    expect(JSON.parse(options.body)).toEqual({
      email: 'visitor@example.com',
      collection_code: 'PUB001',
    });
  });

  test('the intro reads at the pitch size — but stays a paragraph, not a heading', () => {
    // Same first line of words as /login's pitch: .login-pitch, Body XL bold
    // (CA, 2026-09-21). The element differs on purpose: JoinPage's hero <h1> is
    // real words, so this is body copy, and a heading here would put a full
    // sentence in the outline.
    renderJoin();

    const intro = screen.getByText(/Tool Library/);
    expect(intro.tagName).toBe('P');
    expect(intro).toHaveClass('login-pitch');
    expect(screen.queryByRole('heading')).toBeNull();
  });

  test('a server failure reports inline and keeps the form usable', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      json: async () => ({ error: 'boom' }),
    });
    renderJoin();

    submitEmail();

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Something went wrong. Please try again.'
    );
    // Unlike the boxed pages, this inline variant keeps the form on error.
    expect(screen.getByLabelText(/Email/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Send me a magic link' })).toBeInTheDocument();
  });
});

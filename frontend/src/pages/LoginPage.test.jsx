import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { describe, test, expect, vi, afterEach } from 'vitest';
import LoginPage from './LoginPage';

function renderLogin() {
  return render(
    <MemoryRouter>
      <LoginPage />
    </MemoryRouter>
  );
}

function submitEmail(email = 'lala@example.com') {
  fireEvent.change(screen.getByLabelText(/Email/), { target: { value: email } });
  fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));
}

describe('LoginPage magic-link request (the front door)', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  test('submitting sends the typed email and shows the unified sent message', async () => {
    // The backend answers 200 whether or not the email exists (anti-enumeration),
    // so the page must show one unified message, never "unknown email".
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ message: 'Magic link sent' }),
    });
    renderLogin();

    submitEmail('lala@example.com');

    expect(globalThis.fetch).toHaveBeenCalledTimes(1);
    const [url, options] = globalThis.fetch.mock.calls[0];
    expect(url).toBe('/api/v1/auth/request-link/');
    expect(options.method).toBe('POST');
    expect(JSON.parse(options.body)).toEqual({ email: 'lala@example.com' });

    expect(
      await screen.findByText(/If this email is registered, your magic link is on its way/)
    ).toBeInTheDocument();
    // The form is replaced — no double submits from this screen.
    expect(screen.queryByLabelText(/Email/)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Try another email' })).toBeInTheDocument();
  });

  test('the result takes the focus the vanished button was holding', async () => {
    // The form is replaced by the message, so the Sign in button the reader had
    // just activated leaves the DOM — and focus with it, down to <body>, costing
    // them their place. HDS's `autofocus` moves focus onto the message instead,
    // which is also the only thing that gets it read out: an inline Notification
    // carries no role, so nothing else would announce it.
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ message: 'Magic link sent' }),
    });
    renderLogin();
    submitEmail();

    const message = await screen.findByText(/your magic link is on its way/);
    await waitFor(() => {
      expect(document.activeElement).not.toBe(document.body);
      expect(message.closest('section')).toContainElement(document.activeElement);
    });
  });

  test('a rate-limited submit says "wait", not "broken"', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 429,
      json: async () => ({ detail: 'Request was throttled.' }),
    });
    renderLogin();

    submitEmail();

    expect(
      await screen.findByText('Too many attempts — please wait a moment and try again.')
    ).toBeInTheDocument();
  });

  test('a server failure shows a readable error instead of a dead end', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      json: async () => ({ error: 'boom' }),
    });
    renderLogin();

    submitEmail();

    expect(await screen.findByText('Error sending link.')).toBeInTheDocument();
  });

  test('a network failure shows the connection error, and "try another email" restores the form', async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(new TypeError('Failed to fetch'));
    renderLogin();

    submitEmail();

    expect(await screen.findByText('Connection error.')).toBeInTheDocument();

    // The locked-out user can always get back to a working form.
    fireEvent.click(screen.getByRole('button', { name: 'Try another email' }));
    expect(screen.getByLabelText(/Email/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Sign in' })).toBeInTheDocument();
  });
});

describe('LoginPage privacy claim (the promise the front door makes)', () => {
  test('states there is no cookie banner because there is nothing to consent to', () => {
    // This is a public, checkable claim, not decoration: it is what justifies
    // shipping the app without a consent banner. If the app ever gains a
    // tracker, this sentence becomes a lie and must be removed deliberately.
    renderLogin();
    expect(
      screen.getByText(/a cookie banner: there is nothing to consent to/i)
    ).toBeInTheDocument();
  });

  test('the claim carries a link to the README so it can be verified, not just believed', () => {
    renderLogin();
    const verify = screen.getByRole('link', { name: 'you can check' });
    // The anchor matters: it must land on the Privacy section, not the repo root.
    expect(verify).toHaveAttribute('href', 'https://github.com/oiueei/standalone#privacy');
    expect(verify).toHaveAttribute('rel', expect.stringContaining('noopener'));
  });

  test('the per-deployment operator note stays hidden when no operator wrote one', () => {
    // The standalone repo ships login.operator empty — a self-hoster must never
    // inherit a claim about someone else's servers or whereabouts.
    const { container } = renderLogin();
    const paragraphs = [...container.querySelectorAll('p')];
    expect(paragraphs.some((p) => p.textContent.trim() === '')).toBe(false);
  });

  test('the front door says out loud that OIUEEI is in alpha, right under the door', () => {
    // The same sentence the FAQ and the legal notice carry (common.alphaNotice).
    // It sits between the sign-in button and the prose (CA, 2026-09-21): the
    // whole point of the brick is that nobody signs in without having met it,
    // which a paragraph further down the page cannot promise.
    renderLogin();
    const notice = screen.getByText(/OIUEEI is in alpha: nothing is finished/i);
    const signIn = screen.getByRole('button', { name: 'Sign in' });
    const licence = screen.getByText(/OIUEEI's code is open source under the EUPL-1.2/i);
    expect(signIn.compareDocumentPosition(notice) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(notice.compareDocumentPosition(licence) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  test('the way to reach a human sits at the foot, next to the legal link', () => {
    // CA, 2026-09-21. Both are looked for deliberately; neither belongs
    // between a returning member and the field they came for.
    renderLogin();
    const help = screen.getByRole('link', { name: /Trouble signing in/i });
    const legal = screen.getByRole('link', { name: 'Legal notice & privacy' });
    expect(help.compareDocumentPosition(legal) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    const licence = screen.getByText(/OIUEEI's code is open source under the EUPL-1.2/i);
    expect(licence.compareDocumentPosition(help) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});

describe('LoginPage layout: the door first, the reading after', () => {
  // CA's ordering (2026-09-21): title, then the form, then the way in for
  // someone with no account — and every explanatory paragraph below those.
  // Someone who already has an account should not have to scroll past the
  // manifesto to reach the one field they came for.
  test('the pitch is a heading in the page outline, not a bold paragraph', () => {
    renderLogin();
    const pitch = screen.getByRole('heading', {
      name: /Share what you have with the people around you/i,
    });
    // h2, not h4: the hero's <h1> is the logo, and skipping to 4 breaks the
    // outline (axe's heading-order). The Heading-4 SIZE lives in .login-pitch.
    expect(pitch.tagName).toBe('H2');
    expect(pitch).toHaveClass('login-pitch');
  });

  test('the email field comes before every explanatory paragraph', () => {
    renderLogin();
    const email = screen.getByLabelText(/Email/);
    for (const text of [
      /OIUEEI's code is open source under the EUPL-1.2/i,
      /a cookie banner: there is nothing to consent to/i,
    ]) {
      const prose = screen.getByText(text);
      expect(
        email.compareDocumentPosition(prose) & Node.DOCUMENT_POSITION_FOLLOWING,
        `"${prose.textContent.slice(0, 40)}…" must sit below the form`
      ).toBeTruthy();
    }
  });

  test('the page no longer repeats what OIUEEI is above the form', () => {
    // login.description was deleted outright (CA, 2026-09-21) — the licence
    // paragraph below already says the same in fewer words, and this one stood
    // between a returning member and the field they came for.
    renderLogin();
    expect(screen.queryByText(/Create a collection — things to gift, sell, rent/i)).toBeNull();
  });
});

describe('LoginPage hero title-logo (S9)', () => {
  test('the h1 keeps the accessible name "OIUEEI" even though the logo replaces the text', () => {
    render(
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>
    );
    // The logo is a decorative masked <span>, not text — aria-label on the h1
    // is what actually carries the accessible name here.
    const heading = screen.getByRole('heading', { name: 'OIUEEI' });
    expect(heading.tagName).toBe('H1');
    expect(heading).toHaveTextContent('');
  });
});

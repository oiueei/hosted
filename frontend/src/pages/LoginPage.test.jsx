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

  test('the hero suppresses the 40px watermark so there is never a double logo', () => {
    const { container } = render(
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>
    );
    expect(container.querySelector('.form-hero')).toHaveClass('form-hero--no-watermark');
  });
});

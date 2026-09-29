import { render, screen, fireEvent, act, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
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

  test('joining sends the email and the share token — never a language field', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ message: 'Magic link sent' }),
    });
    renderShareVariant();

    submitEmail('newcomer@example.com');

    await screen.findByText(/Magic link sent! Check your inbox/);
    const [url, options] = globalThis.fetch.mock.calls[0];
    expect(url).toBe('/api/v1/auth/join/');
    expect(options.method).toBe('POST');
    // No `language` — sending the page's current UI language used to get it
    // stamped permanently onto the new member, outranking the collection's
    // own language for every email to them from then on (CA's report,
    // 2026-09-15). `share_token` targets the shared collection; the backend
    // now resolves the newcomer's very first magic link from it instead.
    expect(JSON.parse(options.body)).toEqual({
      email: 'newcomer@example.com',
      share_token: 'TOKEN123',
    });
  });

  test('success replaces the form and shows the close-tab line', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ message: 'Magic link sent' }),
    });
    renderShareVariant();

    submitEmail();

    await screen.findByText(/Magic link sent! Check your inbox/);
    expect(screen.getByText(/You can close this tab now/)).toBeInTheDocument();
    // Not flush against the notice above it (CA, 2026-09-21) — the line is
    // the message's quiet coda, not a footnote stapled to the box.
    expect(screen.getByText(/You can close this tab now/)).toHaveStyle({
      marginTop: 'var(--spacing-s)',
    });
    expect(screen.queryByLabelText(/Email/)).not.toBeInTheDocument();
  });

  test('a server failure shows a readable error, not the success screen', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      json: async () => ({ error: 'boom' }),
    });
    renderShareVariant();

    submitEmail();

    expect(await screen.findByText('Error sending link.')).toBeInTheDocument();
    expect(screen.queryByText(/You can close this tab now/)).not.toBeInTheDocument();
  });

  test('two submits in the same tick send only one magic link', async () => {
    // Every accepted join emails a magic link, so a double submit mails a
    // stranger twice. `disabled={loading}` handles the ordinary double-click —
    // React flushes discrete events synchronously, so the button is already
    // disabled by the second one. What it cannot catch is two submit events
    // dispatched before any re-render: both run the same closure, where the
    // `loading` state is still false. Only useJoin's ref guard sees the first
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

describe('MagicLinkJoinPage footer children (a deployment door adds its own link)', () => {
  test('children render under the form; SharePage passes none and gets nothing extra', () => {
    // Upstream: no children.
    renderShareVariant();
    expect(screen.queryByRole('link', { name: 'A deployment link' })).not.toBeInTheDocument();

    // A deployment's door — e.g. the hosted /popin pointing at its /faq.
    render(
      <MemoryRouter>
        <MagicLinkJoinPage
          ns="share"
          docTitleKey="titles.share"
          titleKey="share.pageTitle"
          descriptionKey="share.pageDescription"
        >
          <a href="/faq">A deployment link</a>
        </MagicLinkJoinPage>
      </MemoryRouter>
    );
    expect(screen.getByRole('link', { name: 'A deployment link' })).toHaveAttribute('href', '/faq');
  });
});

describe('MagicLinkJoinPage presentation (the door matches the front door)', () => {
  test('the intro reads at the pitch size — but stays a paragraph, not a heading', () => {
    // Same first line of words as /login's pitch: .login-pitch, Body XL bold.
    // The element differs on purpose: this page's hero <h1> is real words
    // ("Join us on OIUEEI"), so the intro is body copy and a heading here
    // would put a full sentence in the outline.
    renderShareVariant();
    const intro = screen.getByText(/Enter your email and we'll send you a magic link/);
    expect(intro.tagName).toBe('P');
    expect(intro).toHaveClass('login-pitch');
    expect(
      screen.getByRole('heading', { level: 1, name: 'Join us on OIUEEI' })
    ).toBeInTheDocument();
    expect(screen.queryByRole('heading', { level: 2 })).not.toBeInTheDocument();
  });

  test("the collection's own description is met in the hero, not repeated below it", () => {
    // SharePage resolves the owner's description from the preview and hands it
    // over; it belongs with the title in the koros band (PageLayout's
    // `description` slot), where every other page carries it — not as a quiet
    // paragraph under the form.
    const { container } = render(
      <MemoryRouter>
        <MagicLinkJoinPage
          ns="share"
          docTitleKey="titles.share"
          titleKey="share.pageTitle"
          descriptionKey="share.pageDescription"
          collectionDescription="We share the tools we have with the rest of the group."
        />
      </MemoryRouter>
    );
    const heroText = container.querySelector('.form-hero-text');
    expect(heroText).not.toBeNull();
    expect(heroText).toHaveTextContent('We share the tools we have with the rest of the group.');
    // Once, in the hero — no muted duplicate in the page body.
    expect(
      screen.getAllByText(/We share the tools we have with the rest of the group\./)
    ).toHaveLength(1);
  });

  function renderWithDescription(collectionDescription) {
    return render(
      <MemoryRouter>
        <MagicLinkJoinPage
          ns="share"
          docTitleKey="titles.share"
          titleKey="share.pageTitle"
          descriptionKey="share.pageDescription"
          collectionDescription={collectionDescription}
        />
      </MemoryRouter>
    );
  }

  test("the collection's description is Markdown, so bold and lists arrive as such", () => {
    // What a curator writes for CollectionPage reaches a stranger through a shared link. Handed
    // over as a plain string, the `**` showed as typed and the list ran into one line — on the
    // first screen of the funnel, opened from a chat.
    const { container } = renderWithDescription(
      '**Horario**\n\n- Lunes de 10 a 12\n- Jueves de 17 a 19'
    );

    const heroText = container.querySelector('.form-hero-text');
    expect(within(heroText).getByText('Horario').tagName).toBe('STRONG');
    expect(
      within(heroText)
        .getAllByRole('listitem')
        .map((li) => li.textContent)
    ).toEqual(['Lunes de 10 a 12', 'Jueves de 17 a 19']);
    expect(heroText).not.toHaveTextContent('**');
    // PageLayout's `.form-hero-text` is the only one: MarkdownText's own class would double the
    // font size, padding and colour it sets.
    expect(container.querySelectorAll('.form-hero-text')).toHaveLength(1);
  });

  test('HTML in the description is still shown as text, never run', () => {
    // The string used to be escaped by React; MarkdownText injects HTML, so its own escaping is
    // now what stands between an owner's text and the page.
    const { container } = renderWithDescription('<img src=x onerror=alert(1)> and <b>bold</b>');

    const heroText = container.querySelector('.form-hero-text');
    expect(heroText.querySelector('img')).toBeNull();
    expect(heroText.querySelector('b')).toBeNull();
    expect(heroText).toHaveTextContent('<img src=x onerror=alert(1)> and <b>bold</b>');
  });

  test('"Already have an account" is a full-width button-shaped link, not bare text', () => {
    // The mirror of the front door's "new here?" secondary button: one
    // ButtonLink (one <a>, one tab stop) carrying the secondary tokens, so the
    // two doors answer each other in the same shape.
    renderShareVariant();
    const link = screen.getByRole('link', { name: 'Already have an account? Sign in →' });
    expect(link).toHaveClass('button-link--full');
    expect(link).toHaveAttribute('href', '/login');
  });
});

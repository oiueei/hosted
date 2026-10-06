import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { describe, test, expect, vi, afterEach, beforeEach } from 'vitest';
import i18n from '../i18n';
import JoinToAct from './JoinToAct';

// A PROPRIETARY lending library, as the collection endpoint describes it once it has
// loaded: the door names what a member can do there, so it needs both fields.
function renderJoin(props = {}) {
  return render(
    <MemoryRouter>
      <JoinToAct
        collectionCode="PUB001"
        collectionHeadline="Tool Library"
        mode="PROPRIETARY"
        allowedThingTypes={['LEND_THING']}
        {...props}
      />
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
    // own language for every email to them from then on.
    // The backend now resolves their very first magic link from
    // the collection instead.
    expect(JSON.parse(options.body)).toEqual({
      email: 'visitor@example.com',
      collection_code: 'PUB001',
    });
  });

  // Somebody from another group who pressed "Request" on a public group, chose
  // "already have an account" and ended up on Home: the same failure as a session
  // that ran out, in small. Sign-in now brings them back to what they came for.
  test('the door does not link to /legal itself — the site footer does', () => {
    // It used to repeat the footer's "Legal notice & privacy" link under the
    // form. The page this renders in already carries the footer.
    const { container } = renderJoin();

    expect(container.querySelector('a[href="/legal"]')).toBeNull();
    expect(screen.queryByRole('link', { name: /legal notice|privacy/i })).toBeNull();
  });

  test('"already have an account" returns to the thing they were looking at', () => {
    renderJoin({ thingCode: 'THG001' });

    expect(screen.getByRole('link', { name: /Already have an account/ })).toHaveAttribute(
      'href',
      '/login?next=%2Fcollections%2FPUB001%2Fthings%2FTHG001'
    );
  });

  test('"already have an account" returns to the group when there was no thing', () => {
    renderJoin();

    expect(screen.getByRole('link', { name: /Already have an account/ })).toHaveAttribute(
      'href',
      '/login?next=%2Fcollections%2FPUB001'
    );
  });

  test('the intro reads at the pitch size — but stays a paragraph, not a heading', () => {
    // Same first line of words as /login's pitch: .login-pitch, Body XL bold.
    // The element differs on purpose: JoinPage's hero <h1> is
    // real words, so this is body copy, and a heading here would put a full
    // sentence in the outline.
    renderJoin();

    const intro = screen.getByText(/Tool Library/);
    expect(intro.tagName).toBe('P');
    expect(intro).toHaveClass('login-pitch');
    expect(screen.queryByRole('heading')).toBeNull();
  });

  test('the close-the-tab line is not flush against the notice above it', async () => {
    // The line is the message's quiet coda, not a footnote
    // stapled to the box. Same gap MagicLinkJoinPage gives it.
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ message: 'Magic link sent' }),
    });
    renderJoin();

    submitEmail();

    const line = await screen.findByText(/You can close this tab now/);
    expect(line).toHaveStyle({ marginTop: 'var(--spacing-s)' });
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

/**
 * The door's first line promises what a member of THIS collection can do. It used to
 * say the same four verbs everywhere — "request, reserve, ask or add your own things"
 * — to someone about to join a reservations collection, where nothing is requested
 * and a member adds nothing. The verbs now come from the thing types
 * the collection allows and from its mode; "ask" is not a verb the door promises.
 */
describe('JoinToAct — the first line says what a member can do in THIS collection', () => {
  const TAIL = {
    es: 'Escribe tu correo y te enviaremos un enlace mágico: sin contraseña ni formularios de registro.',
    ca: "Escriu el teu correu i t'enviarem un enllaç màgic: sense contrasenya ni formularis de registre.",
    en: "Enter your email and we'll send you a magic link — no password, no sign-up form.",
  };

  beforeEach(() => localStorage.clear());
  afterEach(async () => {
    await i18n.changeLanguage('en');
    localStorage.removeItem('i18nextLng');
  });

  const pitch = (name) => screen.getByText(new RegExp(name)).textContent;

  // What the five real shapes of collection say, word for word.
  const EXAMPLES = [
    {
      what: 'a reservations collection (a makerspace), in Catalan: reserve, and nothing else',
      language: 'ca',
      mode: 'PROPRIETARY',
      types: ['RESERVE_THING'],
      name: 'Reserva de màquines del Fab Casa del Mig',
      says: `Uneix-te per reservar a Reserva de màquines del Fab Casa del Mig. ${TAIL.ca}`,
      never: /afegir|demanar/,
    },
    {
      what: 'a PROPRIETARY lending library, in Spanish: borrow, and nobody adds',
      language: 'es',
      mode: 'PROPRIETARY',
      types: ['LEND_THING'],
      name: 'Biblioteca de herramientas',
      says: `Únete para tomar prestado en Biblioteca de herramientas. ${TAIL.es}`,
      never: /añadir|reservar/,
    },
    {
      what: 'a COMMUNITY lending library, in Spanish: borrow and add your own',
      language: 'es',
      mode: 'COMMUNITY',
      types: ['LEND_THING'],
      name: 'Chalmecoses',
      says: `Únete para tomar prestado y añadir tus propias cosas en Chalmecoses. ${TAIL.es}`,
      never: /reservar/,
    },
    {
      what: 'a COMMUNITY group that gives and lends, in Catalan: three verbs, one "i"',
      language: 'ca',
      mode: 'COMMUNITY',
      types: ['GIFT_THING', 'LEND_THING'],
      name: 'Eines del barri',
      says: `Uneix-te per demanar, demanar prestat i afegir les teves coses a Eines del barri. ${TAIL.ca}`,
      never: /reservar|comprar|llogar/,
    },
    {
      what: 'a COMMUNITY group with no restriction, in English: the four types and add your own',
      language: 'en',
      mode: 'COMMUNITY',
      types: [],
      name: 'Tool Library',
      says: `Join to claim, buy, borrow, rent, and add your own things in Tool Library. ${TAIL.en}`,
      never: /reserve/,
    },
  ];

  test.each(EXAMPLES)('$what', async ({ language, mode, types, name, says, never }) => {
    await i18n.changeLanguage(language);
    renderJoin({ mode, allowedThingTypes: types, collectionHeadline: name });

    expect(pitch(name)).toBe(says);
    expect(pitch(name)).not.toMatch(never);
  });

  test.each(EXAMPLES)('never promises asking a question: $what', async (example) => {
    await i18n.changeLanguage(example.language);
    renderJoin({
      mode: example.mode,
      allowedThingTypes: example.types,
      collectionHeadline: example.name,
    });

    expect(pitch(example.name)).not.toMatch(/preguntar|ask/i);
  });

  test('a type the collection does not allow never shows up', () => {
    renderJoin({ mode: 'PROPRIETARY', allowedThingTypes: ['GIFT_THING'] });

    const said = pitch('Tool Library');
    expect(said).toMatch(/^Join to claim in Tool Library\./);
    expect(said).not.toMatch(/buy|borrow|rent|reserve|add your own/);
  });

  test('the verbs come in the cards’ order, not in the order the API listed the types', () => {
    renderJoin({ mode: 'PROPRIETARY', allowedThingTypes: ['RENT_THING', 'GIFT_THING'] });

    expect(pitch('Tool Library')).toMatch(/^Join to claim and rent in Tool Library\./);
  });

  test('until the collection has loaded the door says the generic sentence, not a guess', () => {
    renderJoin({ mode: '', allowedThingTypes: [] });

    expect(
      screen.getByText(/^Join to request, reserve, ask a question or add your own things\./)
    ).toBeInTheDocument();
    expect(screen.queryByText(/Tool Library/)).not.toBeInTheDocument();
  });

  test('types the door has no verb for leave the generic sentence, not a hole in it', () => {
    renderJoin({ mode: 'PROPRIETARY', allowedThingTypes: ['SHARE_THING'] });

    expect(
      screen.getByText(/^Join to request, reserve, ask a question or add your own things\./)
    ).toBeInTheDocument();
  });
});

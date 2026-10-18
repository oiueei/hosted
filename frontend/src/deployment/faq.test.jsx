import { render, screen, waitFor } from '@testing-library/react';
import { axe, toHaveNoViolations } from 'jest-axe';
import { vi, describe, test, expect, beforeEach, afterEach } from 'vitest';
import i18n from 'i18next';

import './testI18n';
import { settle, switchLanguage, press } from '../test/settle';
import App from '../App';
import { loadFaqEntries } from './faq';
import faqEs from './faq/es';
import faqCa from './faq/ca';
import faqEn from './faq/en';

/**
 * The help page, and the promises its shape exists to keep.
 *
 * A question without its own anchor cannot be pasted into a chat; a placeholder
 * that ships reads as a fact to whoever finds it; an answer added to one
 * language and forgotten in the other two leaves readers of those languages
 * with a page that is quietly missing something. All three fail silently, which
 * is why they are pinned here rather than left to a proofread.
 */

expect.extend(toHaveNoViolations);

const LANGUAGES = [
  ['es', faqEs],
  ['ca', faqCa],
  ['en', faqEn],
];

// The question about getting in touch — who tells whom, and by what route — pinned letter by
// letter: its answer says what OIUEEI does and does not do between a requester and whoever
// runs the thing, so a rephrasing is a change to that, not a copy edit.
const CONTACTO = {
  es: {
    q: '¿Cómo se ponen en contacto quien pide una cosa y quien la gestiona?',
    a: 'Por correo, y en un solo sentido. Cuando pides una cosa, a quien la gestiona le llegan con la solicitud tu nombre y tu email —el que usas para entrar en OIUEEI—, para que pueda escribirte y quedar; también lo ve en «Solicitudes para mí». Su email no se te muestra: lo tendrás cuando te escriba. OIUEEI no tiene chat, y el pago o la entrega los acordáis vosotros.',
  },
  ca: {
    q: 'Com es posen en contacte qui demana una cosa i qui la gestiona?',
    a: "Per correu, i en un sol sentit. Quan demanes una cosa, a qui la gestiona li arriben amb la sol·licitud el teu nom i el teu email —el que fas servir per entrar a OIUEEI—, perquè et pugui escriure i quedar; també el veu a «Sol·licituds per a mi». El seu email no se't mostra: el tindràs quan t'escrigui. OIUEEI no té xat, i el pagament o el lliurament els acordeu vosaltres.",
  },
  en: {
    q: 'How do the person asking for a thing and the person who runs it get in touch?',
    a: "By email, and one way only. When you ask for a thing, whoever runs it gets your name and your email — the one you sign in to OIUEEI with — along with the request, so they can write to you and arrange things; they also see it under “Requests to me”. Their email isn't shown to you: you'll have it when they write. OIUEEI has no chat, and payment or hand-over is up to the two of you.",
  },
};

// What `reservas` says about who answers a request, now and what it used to say: in a COMMUNITY
// the one who accepts or declines is whoever runs the thing, not whoever runs the collection.
const RESERVAS = {
  es: { now: 'quien gestiona la cosa acepta o rechaza', gone: 'la colección' },
  ca: { now: 'qui gestiona la cosa accepta o rebutja', gone: 'la col·lecció' },
  en: { now: 'whoever runs the thing accepts or declines', gone: 'the collection' },
};

window.scrollTo = vi.fn();
globalThis.fetch = vi.fn(() =>
  Promise.resolve({ ok: false, status: 400, json: () => Promise.resolve({}) })
);

beforeEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
});

afterEach(async () => {
  await switchLanguage(i18n, 'en');
});

describe('the app serves the help page', () => {
  test('/faq answers with the questions and not with the 404 page', async () => {
    window.history.pushState({}, '', '/faq');
    render(<App />);

    expect(await screen.findByRole('heading', { name: faqEn[0].q, level: 2 })).toBeInTheDocument();
    await settle(globalThis.fetch);
    await waitFor(() => expect(document.title).toMatch(/frequently asked questions/i));
  });

  test('a Catalan reader gets the Catalan answers, not the English ones', async () => {
    await switchLanguage(i18n, 'ca');
    window.history.pushState({}, '', '/faq');
    render(<App />);

    expect(await screen.findByRole('heading', { name: faqCa[0].q, level: 2 })).toBeInTheDocument();
    await settle(globalThis.fetch);
    expect(screen.queryByRole('heading', { name: faqEn[0].q, level: 2 })).toBeNull();
  });

  test('every question is an anchor somebody can link to', async () => {
    window.history.pushState({}, '', '/faq');
    render(<App />);

    await screen.findByRole('heading', { name: faqEn[0].q, level: 2 });
    await settle(globalThis.fetch);

    for (const entry of faqEn) {
      const heading = document.getElementById(entry.id);
      expect(heading, `no anchor for "${entry.id}"`).not.toBeNull();
      expect(heading.tagName).toBe('H2');
      expect(heading.textContent).toBe(entry.q);
    }
  });

  test('a destination inside the app stays inside the app', async () => {
    window.history.pushState({}, '', '/faq');
    render(<App />);

    await screen.findByRole('heading', { name: faqEn[0].q, level: 2 });
    await settle(globalThis.fetch);

    // `MarkdownText` opens every anchor it renders in a new tab, which is why
    // these live in their own field. If one ever migrates into the Markdown,
    // this is what notices: /legal would start opening in a second window.
    const internal = faqEn.filter((entry) => entry.link);
    expect(internal.length).toBeGreaterThan(0);
    for (const { link } of internal) {
      const anchor = document.querySelector(`a[href="${link.to}"]`);
      expect(anchor, `no in-app link to ${link.to}`).not.toBeNull();
      expect(anchor.getAttribute('target')).toBeNull();
    }
  });

  test('the page has no accessibility violations', async () => {
    window.history.pushState({}, '', '/faq');
    const { container } = render(<App />);

    await screen.findByRole('heading', { name: faqEn[0].q, level: 2 });
    await settle(globalThis.fetch);

    expect(await axe(container)).toHaveNoViolations();
  });
});

describe('the three languages stay one page', () => {
  test('same questions, same order, same anchors', () => {
    const ids = faqEs.map((entry) => entry.id);
    for (const [lang, entries] of LANGUAGES) {
      expect(
        entries.map((entry) => entry.id),
        `${lang} drifted from es`
      ).toEqual(ids);
    }
  });

  test('a question that links somewhere links there in every language', () => {
    for (const [index, entry] of faqEs.entries()) {
      for (const [lang, entries] of LANGUAGES) {
        expect(entries[index].link?.to, `${lang}/${entry.id} disagrees on the destination`).toBe(
          entry.link?.to
        );
      }
    }
  });

  test('every answer is written, in every language', () => {
    for (const [lang, entries] of LANGUAGES) {
      for (const entry of entries) {
        expect(`${entry.q} ${entry.a}`, `${lang}/${entry.id}`).not.toMatch(/\{\{|TODO|TBD|XXX/);
        expect(entry.q.length, `${lang}/${entry.id} has no question`).toBeGreaterThan(0);
        expect(entry.a.length, `${lang}/${entry.id} has no answer`).toBeGreaterThan(0);
      }
    }
  });

  test('the ids are unique, because they are public URLs', () => {
    const ids = faqEs.map((entry) => entry.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  test('each language loads its own answers, and an unknown one falls back', async () => {
    for (const [lang, entries] of LANGUAGES) {
      await expect(loadFaqEntries(lang)).resolves.toBe(entries);
    }
    await expect(loadFaqEntries('pt')).resolves.toBe(faqEn);
  });
});

describe('the question about getting in touch', () => {
  test.each(LANGUAGES)(
    '%s: it comes right after "reservas", word for word, with no link',
    (lang, entries) => {
      const index = entries.findIndex((entry) => entry.id === 'reservas');
      const entry = entries[index + 1];

      expect(entry.id).toBe('contacto');
      expect(entry.q).toBe(CONTACTO[lang].q);
      expect(entry.a).toBe(CONTACTO[lang].a);
      expect(entry.link).toBeUndefined();
    }
  );

  test.each(LANGUAGES)(
    '%s: "reservas" says whoever runs the thing, not the collection',
    (lang, entries) => {
      const { a } = entries.find((entry) => entry.id === 'reservas');

      expect(a).toContain(RESERVAS[lang].now);
      expect(a).not.toContain(RESERVAS[lang].gone);
    }
  );

  test.each(LANGUAGES)(
    '%s: the page shows it as the next section after "reservas"',
    async (lang, entries) => {
      await switchLanguage(i18n, lang);
      window.history.pushState({}, '', '/faq');
      render(<App />);

      await screen.findByRole('heading', { name: entries[0].q, level: 2 });
      await settle(globalThis.fetch);

      const ids = Array.from(document.querySelectorAll('h2[id]')).map((heading) => heading.id);
      expect(ids.indexOf('contacto')).toBe(ids.indexOf('reservas') + 1);
      const heading = document.getElementById('contacto');
      expect(heading.textContent).toBe(CONTACTO[lang].q);
      expect(screen.getByText(CONTACTO[lang].a)).toBeInTheDocument();
      // An answer, not a way to somewhere else: no in-app link under it.
      expect(heading.closest('section').querySelector('a')).toBeNull();
    }
  );
});

describe('the ways in', () => {
  // Three of the FAQ's doors are pinned here. The fourth — the entry under the form
  // on /popin — is handed to `MagicLinkJoinPage`'s `children` slot, and
  // `pages/PopInPage.test.jsx` pins that wiring.
  test('/login offers it, which is what faqPath is for', async () => {
    window.history.pushState({}, '', '/login');
    render(<App />);

    await waitFor(() => expect(document.querySelector('a[href="/faq"]')).not.toBeNull());
    await settle(globalThis.fetch);
  });

  test('/welcome offers it, where somebody already inside asks', async () => {
    window.history.pushState({}, '', '/welcome');
    render(<App />);

    await waitFor(() => expect(document.querySelector('a[href="/faq"]')).not.toBeNull());
    await settle(globalThis.fetch);
  });

  test('/legal offers it, and says which of the two is binding', async () => {
    window.history.pushState({}, '', '/legal');
    render(<App />);

    // Written inside the legal Markdown, so `MarkdownText` renders it: a path on
    // this site, so it opens in the same tab and a plain click is followed by the
    // router, like the links on the help page itself.
    const link = await waitFor(() => {
      const found = document.querySelector('a[href="/faq"]');
      expect(found).not.toBeNull();
      return found;
    });
    expect(link.getAttribute('target')).toBeNull();
    await settle(globalThis.fetch);

    await press(link);
    await settle(globalThis.fetch);
    await waitFor(() => expect(window.location.pathname).toBe('/faq'));
  });
});

// The question for whoever runs a group, copied letter by letter: it tells people what data
// they hold and what to do with it, so a rephrasing is a change to that, not a copy edit.
const DINAMIZAR = {
  es: {
    q: 'Si dinamizas un grupo',
    a: 'Puedes invitar y quitar miembros, escribir a todo el grupo, editar la colección y pasar a otros a dinamizarla contigo. En un grupo que lleva el equipo (no en una comunidad), también ves y respondes las solicitudes de todas sus cosas. Con eso tienes datos de otras personas: el correo de cada miembro, quién pide qué y cuándo. La copia de la colección (el JSON del menú) los lleva todos: guárdala en un sitio seguro y no la reenvíes. Usa esos correos solo para el grupo. Si dejas de dinamizar, borra las copias que tengas.',
  },
  ca: {
    q: 'Si dinamitzes un grup',
    a: "Pots convidar i treure membres, escriure a tot el grup, editar la col·lecció i fer que altres la dinamitzin amb tu. En un grup que porta l'equip (no en una comunitat), també veus i respons les sol·licituds de totes les seves coses. Amb això tens dades d'altres persones: el correu de cada membre, qui demana què i quan. La còpia de la col·lecció (el JSON del menú) les porta totes: guarda-la en un lloc segur i no la reenviïs. Fes servir aquests correus només per al grup. Si deixes de dinamitzar, esborra les còpies que tinguis.",
  },
  en: {
    q: 'If you run a group',
    a: "You can invite and remove members, write to the whole group, edit the collection and bring others in to run it with you. In a group the team runs (not a community), you also see and answer the requests for all of its things. That gives you other people's data: each member's email, who asks for what and when. The collection copy (the JSON in the menu) carries all of it: keep it somewhere safe and don't forward it. Use those emails only for the group. If you stop running it, delete the copies you have.",
  },
};

describe('the guide for whoever runs a group', () => {
  test.each(LANGUAGES)(
    '%s: the question is there with its stable anchor, word for word',
    (lang, entries) => {
      const entry = entries.find((e) => e.id === 'dinamizar');

      expect(entry).toBeDefined();
      expect({ q: entry.q, a: entry.a }).toEqual(DINAMIZAR[lang]);
    }
  );

  test('the path the app links to leads to that question, in every language', async () => {
    const { curatorGuidePath } = await import('./index');
    const [path, anchor] = curatorGuidePath.split('#');

    expect(path).toBe('/faq');
    for (const [, entries] of LANGUAGES) {
      expect(
        entries.some((e) => e.id === anchor),
        `no question for #${anchor}`
      ).toBe(true);
    }
  });

  test('opening the guide path lands on the question', async () => {
    const { curatorGuidePath } = await import('./index');
    const scrolled = vi.fn();
    Element.prototype.scrollIntoView = scrolled;
    window.history.pushState({}, '', curatorGuidePath);
    render(<App />);

    const heading = await screen.findByRole('heading', { name: DINAMIZAR.en.q, level: 2 });
    await settle(globalThis.fetch);

    await waitFor(() => expect(scrolled).toHaveBeenCalled());
    expect(heading.id).toBe('dinamizar');
    expect(scrolled.mock.contexts.at(-1)).toBe(heading);
  });
});

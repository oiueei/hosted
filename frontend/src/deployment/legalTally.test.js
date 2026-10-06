import { describe, test, expect } from 'vitest';
import es from '../legal/es';
import ca from '../legal/ca';
import en from '../legal/en';
import { externalForms } from './index';

/**
 * The privacy section of `/legal` names Tally, and says what it receives. It was the
 * feedback form alone; "Contact us" and "Request access" are
 * Tally forms now too (`externalForms`), so the paragraph names all three. The wording
 * is the operator's own, and pinned as written: a rephrasing here is a change
 * to what the operator tells people it does with their data, not a copy edit.
 *
 * And the thing that makes it a guard and not a snapshot: **every host a form of this
 * deployment lives on must be named** in the text of each language. A fourth form on
 * another service, added to `externalForms` without a line in `/legal`, goes red here.
 */
const APPROVED = {
  es: [
    es,
    'Tally (los formularios de contacto, de sugerencias y de solicitud de acceso, Bélgica — solo recibe lo que escribes en ellos)',
    'Tally (el formulario de sugerencias, Bélgica — solo recibe algo si escribes en él)',
  ],
  ca: [
    ca,
    "Tally (els formularis de contacte, de suggeriments i de sol·licitud d'accés, Bèlgica — només rep el que hi escrius)",
    'Tally (el formulari de suggeriments, Bèlgica — només rep res si hi escrius)',
  ],
  en: [
    en,
    'Tally (the contact, feedback and access-request forms, Belgium — it only receives what you write in them)',
    'Tally (the feedback form, Belgium — it receives nothing unless you write in it)',
  ],
};

describe('/legal says what Tally receives', () => {
  test.each(Object.keys(APPROVED))('%s: the approved wording, as written', (lang) => {
    const [text, approved] = APPROVED[lang];

    expect(text).toContain(approved);
  });

  test.each(Object.keys(APPROVED))('%s: the old "feedback form only" wording is gone', (lang) => {
    const [text, , old] = APPROVED[lang];

    expect(text).not.toContain(old);
  });

  test.each(Object.keys(APPROVED))('%s: Tally is named once, among the processors', (lang) => {
    const [text] = APPROVED[lang];

    expect(text.match(/Tally/g)).toHaveLength(1);
  });

  test('ca: the apostrophe of "d\'accés" is the straight one, like the others in the file', () => {
    expect(ca).not.toMatch(/[’‘]/);
    expect(ca).toContain("sol·licitud d'accés");
  });
});

describe('every host a form lives on is named in /legal', () => {
  const hosts = [
    ...new Set(
      Object.values(externalForms)
        .flatMap((byLanguage) => Object.values(byLanguage))
        .map((url) => new URL(url).hostname)
    ),
  ];

  test('this deployment’s forms are all on one service, Tally', () => {
    expect(hosts).toEqual(['tally.so']);
  });

  test.each(Object.keys(APPROVED))('%s names each of them', (lang) => {
    const [text] = APPROVED[lang];

    for (const host of hosts) {
      // `tally.so` → the name a person would read: "Tally".
      const brand = host.split('.').at(-2);
      expect(text.toLowerCase(), `${host} is not named in the ${lang} /legal`).toContain(brand);
    }
  });
});

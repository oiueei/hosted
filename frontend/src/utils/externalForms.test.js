import { describe, test, expect, beforeEach, afterEach, vi } from 'vitest';

/**
 * `externalFormUrl(kind, language)` — the address of a form a deployment hosts
 * elsewhere in the place of one of the app's own ways of writing to the team.
 * The `deployment` module is mocked, the only way to exercise a
 * replacement from this repository (upstream's `externalForms` is `null`).
 */
const FORMS = {
  contact: {
    es: 'https://forms.example/c-es',
    ca: 'https://forms.example/c-ca',
    en: 'https://forms.example/c-en',
  },
  feedback: {
    es: 'https://forms.example/f-es',
    ca: 'https://forms.example/f-ca',
    en: 'https://forms.example/f-en',
  },
  requestAccess: {
    es: 'https://forms.example/r-es',
    ca: 'https://forms.example/r-ca',
    en: 'https://forms.example/r-en',
  },
};

async function helperWith(externalForms) {
  vi.resetModules();
  vi.doMock('../deployment', () => ({ externalForms }));
  return (await import('./externalForms')).externalFormUrl;
}

beforeEach(() => vi.resetModules());
afterEach(() => vi.doUnmock('../deployment'));

describe('externalFormUrl', () => {
  test.each([
    ['contact', 'es', 'https://forms.example/c-es'],
    ['contact', 'ca', 'https://forms.example/c-ca'],
    ['contact', 'en', 'https://forms.example/c-en'],
    ['feedback', 'ca', 'https://forms.example/f-ca'],
    ['requestAccess', 'en', 'https://forms.example/r-en'],
  ])('%s in %s is the address of that language', async (kind, language, expected) => {
    const externalFormUrl = await helperWith(FORMS);

    expect(externalFormUrl(kind, language)).toBe(expected);
  });

  test('it is the address as written: nothing is added to it, a query and a fragment included', async () => {
    const written = 'https://forms.example/c-es?utm=oiueei&x=1#start';
    const externalFormUrl = await helperWith({
      contact: { es: written, ca: written, en: written },
    });

    expect(externalFormUrl('contact', 'es')).toBe(written);
    expect(externalFormUrl('contact', 'en')).toBe(written);
  });

  test('a language with no address falls back to es', async () => {
    const externalFormUrl = await helperWith({
      contact: { es: 'https://forms.example/c-es', en: 'https://forms.example/c-en' },
    });

    expect(externalFormUrl('contact', 'ca')).toBe('https://forms.example/c-es');
    // …and one the app does not even have.
    expect(externalFormUrl('contact', 'fr')).toBe('https://forms.example/c-es');
    expect(externalFormUrl('contact', 'en')).toBe('https://forms.example/c-en');
  });

  test('an empty address counts as none', async () => {
    const externalFormUrl = await helperWith({
      contact: { es: 'https://forms.example/c-es', ca: '', en: null },
    });

    expect(externalFormUrl('contact', 'ca')).toBe('https://forms.example/c-es');
    expect(externalFormUrl('contact', 'en')).toBe('https://forms.example/c-es');
  });

  test('with no language at all it is the es one', async () => {
    const externalFormUrl = await helperWith(FORMS);

    expect(externalFormUrl('contact')).toBe('https://forms.example/c-es');
    expect(externalFormUrl('contact', undefined)).toBe('https://forms.example/c-es');
    expect(externalFormUrl('contact', '')).toBe('https://forms.example/c-es');
  });

  test('a regional tag is its language', async () => {
    const externalFormUrl = await helperWith(FORMS);

    expect(externalFormUrl('contact', 'ca-ES')).toBe('https://forms.example/c-ca');
    expect(externalFormUrl('contact', 'EN-gb')).toBe('https://forms.example/c-en');
  });

  test('a kind the deployment has no form for is null, in any language', async () => {
    const externalFormUrl = await helperWith({ contact: FORMS.contact });

    expect(externalFormUrl('feedback', 'es')).toBeNull();
    expect(externalFormUrl('requestAccess', 'ca')).toBeNull();
    expect(externalFormUrl('contact', 'ca')).toBe('https://forms.example/c-ca');
  });

  test('a kind set to null, an empty one, or one that is not a kind: null', async () => {
    const externalFormUrl = await helperWith({
      contact: null,
      feedback: {},
      requestAccess: { ca: 'https://x.example/ca' },
    });

    expect(externalFormUrl('contact', 'es')).toBeNull();
    expect(externalFormUrl('feedback', 'es')).toBeNull();
    // Only a language other than es: nothing to fall back to, so null for the others.
    expect(externalFormUrl('requestAccess', 'ca')).toBe('https://x.example/ca');
    expect(externalFormUrl('requestAccess', 'en')).toBeNull();
    expect(externalFormUrl('nothing-like-it', 'es')).toBeNull();
  });

  test('upstream has no externalForms: null for everything', async () => {
    const externalFormUrl = await helperWith(null);

    for (const kind of ['contact', 'feedback', 'requestAccess']) {
      expect(externalFormUrl(kind, 'es')).toBeNull();
    }
  });

  test('a deployment module that lacks the export altogether is the same as null', async () => {
    vi.resetModules();
    vi.doMock('../deployment', () => ({ externalForms: undefined }));
    const { externalFormUrl } = await import('./externalForms');

    expect(externalFormUrl('contact', 'es')).toBeNull();
  });
});

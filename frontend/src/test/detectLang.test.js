import { describe, test, expect } from 'vitest';
import fs from 'node:fs';
import vm from 'node:vm';

/**
 * `public/detect-lang.js` runs before React mounts (A3), setting html[lang]
 * so the very first paint — and every crawler — sees the right language
 * instead of the static "en" in index.html. It has to stay a plain script a
 * browser can execute with nothing else loaded yet, so it can't import
 * anything this suite could unit-test directly; instead this evaluates the
 * real file's source in a sandboxed context with fake browser globals, the
 * same file a browser actually runs, not a copy of its logic.
 */
const SOURCE = fs.readFileSync('public/detect-lang.js', 'utf8');

function run({ storedLang, navigatorLanguage, navigatorLanguages, storageThrows } = {}) {
  const documentElement = { lang: 'en' };
  const sandbox = {
    document: { documentElement },
    window: {
      localStorage: {
        getItem: (key) => {
          if (storageThrows) throw new Error('storage disabled');
          return key === 'i18nextLng' ? (storedLang ?? null) : null;
        },
      },
    },
    navigator: {
      language: navigatorLanguage,
      languages: navigatorLanguages,
    },
  };
  vm.createContext(sandbox);
  vm.runInContext(SOURCE, sandbox);
  return documentElement.lang;
}

describe('detect-lang.js', () => {
  test('a saved i18next choice wins over the browser language', () => {
    expect(run({ storedLang: 'ca', navigatorLanguage: 'en-US' })).toBe('ca');
  });

  test('falls back to navigator.language when nothing is saved', () => {
    expect(run({ navigatorLanguage: 'es-ES' })).toBe('es');
  });

  test('checks every entry in navigator.languages before giving up', () => {
    expect(run({ navigatorLanguages: ['fr-FR', 'ca-ES'], navigatorLanguage: 'fr-FR' })).toBe('ca');
  });

  test('a retired locale falls back to es, matching src/i18n/index.js', () => {
    // pt/eu/gl map to es in the real i18n config's fallbackLng — the two must
    // agree, or the html[lang] the browser paints first disagrees with the
    // language i18next settles on once it loads.
    expect(run({ navigatorLanguage: 'pt-BR' })).toBe('es');
    expect(run({ navigatorLanguage: 'eu' })).toBe('es');
    expect(run({ navigatorLanguage: 'gl-ES' })).toBe('es');
  });

  test('an unsupported, non-retired language falls back to en', () => {
    expect(run({ navigatorLanguage: 'fr-FR' })).toBe('en');
  });

  test('a locked-down localStorage does not stop the browser-language fallback', () => {
    expect(run({ storageThrows: true, navigatorLanguage: 'ca-ES' })).toBe('ca');
  });

  test('nothing usable at all still leaves a valid lang, not empty or undefined', () => {
    expect(run({})).toBe('en');
  });
});

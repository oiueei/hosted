import { describe, test, expect, beforeEach, afterEach, vi } from 'vitest';

/**
 * `src/i18n/index.js` — the two pieces of real logic in the i18n bootstrap.
 *
 * This directory was excluded from coverage (`vite.config.js`) back when it held
 * nothing but configuration, and the shared test setup replaces the i18next
 * singleton with a minimal English-only `init` (`src/test/i18n-mock.js`). So the
 * real module was never imported by a test and never measured — which was fine
 * until this round put two behaviours in it:
 *
 * 1. **A deployment's own copy survives the language chunk landing.** The bundles
 *    are re-applied on i18next's `loaded` event, not once at startup, because es
 *    and ca arrive later as their own chunks and i18next merges an incoming
 *    bundle *over* what is already there. Registered only at startup, a
 *    deployment's strings would work in English and vanish the moment the
 *    visitor's real language loaded — the worst shape of bug, since English is
 *    what the author of the deployment is most likely testing in.
 *
 * 2. **Every language the picker offers has a chunk to load.** `LAZY_LOCALES` is
 *    a hand-written map, and adding a language means editing it, `supportedLngs`
 *    and `SUPPORTED_LANGUAGES` together. Miss the map and that language silently
 *    renders English forever — no error, nothing red.
 *
 * Each test re-imports the module after `vi.resetModules()`, which hands it a
 * fresh `i18next` singleton rather than the one the shared setup already
 * initialised. That isolation is the whole reason this file can exist.
 */

const KEY = 'stats.downloadStats';
const SPANISH = 'Descargar estadísticas (CSV)';

async function loadI18n(deploymentI18n = {}) {
  vi.resetModules();
  vi.doMock('../deployment', () => ({
    deploymentRoutes: [],
    popInPath: null,
    aboutPath: null,
    deploymentI18n,
  }));
  const { default: i18n } = await import('../i18n');
  return i18n;
}

beforeEach(() => {
  localStorage.clear();
  // Pin the starting language: LanguageDetector reads localStorage first, and a
  // test that began in whatever jsdom's navigator reports would assert about a
  // different language on a different machine.
  localStorage.setItem('i18nextLng', 'en');
});

afterEach(() => {
  vi.doUnmock('../deployment');
});

describe('upstream adds nothing', () => {
  test('with no deployment copy, the language file speaks for itself', async () => {
    const i18n = await loadI18n();

    await i18n.changeLanguage('es');

    // The mechanism is a no-op when there is nothing to apply — an OIUEEI
    // checkout reads exactly what is in `locales/es.json`.
    expect(i18n.t(KEY)).toBe(SPANISH);
  });
});

describe("a deployment's own copy", () => {
  const DEPLOYMENT = {
    es: { stats: { downloadStats: 'Descargar el informe' } },
  };

  test('survives the Spanish chunk landing on top of it', async () => {
    /* The regression, stated exactly. Without the `loaded` handler this string
       is correct until the es chunk resolves and then silently reverts to the
       product's own wording — in the one language the deployment bothered to
       translate. */
    const i18n = await loadI18n(DEPLOYMENT);

    await i18n.changeLanguage('es');

    expect(i18n.t(KEY)).toBe('Descargar el informe');
    expect(i18n.t(KEY)).not.toBe(SPANISH);
  });

  test('overrides only what it names, leaving the rest of the language intact', async () => {
    // Deep merge, not replace: a deployment that changes one string must not
    // blank the other few hundred in that file.
    const i18n = await loadI18n(DEPLOYMENT);

    await i18n.changeLanguage('es');

    expect(i18n.t('stats.downloadStatsError')).toBe(
      'No se pudieron descargar las estadísticas.'
    );
  });

  test('a language the deployment did not translate is untouched', async () => {
    const i18n = await loadI18n(DEPLOYMENT);

    await i18n.changeLanguage('ca');

    expect(i18n.t(KEY)).not.toBe('Descargar el informe');
    expect(i18n.t(KEY).length).toBeGreaterThan(0);
  });
});

describe('every language the picker offers can actually load', () => {
  test('each one resolves to its own translation, not to English', async () => {
    /* Derived from `SUPPORTED_LANGUAGES` — the list the in-app picker renders —
       rather than from a copy of it here. Adding a language means touching
       `supportedLngs`, `SUPPORTED_LANGUAGES` and the `LAZY_LOCALES` map; miss
       the map and that language falls back to English with no chunk, no error
       and nothing red. This is the test that goes red instead. */
    const i18n = await loadI18n();
    const { SUPPORTED_LANGUAGES } = await import('../i18n');
    const english = i18n.t(KEY);

    expect(SUPPORTED_LANGUAGES.length).toBeGreaterThan(1);

    for (const { code } of SUPPORTED_LANGUAGES) {
      await i18n.changeLanguage(code);
      const translated = i18n.t(KEY);

      expect(translated.length).toBeGreaterThan(0);
      if (code !== 'en') {
        // The chunk really landed: English would mean LAZY_LOCALES has no entry
        // for this code and i18next quietly kept the fallback.
        expect(translated, `${code} fell back to English`).not.toBe(english);
      }
    }
  });
});

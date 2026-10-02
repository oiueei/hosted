import { describe, test, expect } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';
import { STALE_CHUNK_KEY } from '../utils/reloadOnStaleChunk';
import es from '../legal/es';
import ca from '../legal/ca';
import en from '../legal/en';

/**
 * This deployment's public inventory of what the browser stores is its `/legal`
 * page, not the README: that half of `src/test/browserStorage.test.jsx` runs in
 * the standalone only (`describe.runIf(isStandalone)`), so here nothing guards
 * it. This test is that guard.
 *
 * The keys are **scanned**, never listed by hand, so a storage key added
 * upstream appears in this sweep the moment `main` merges into `hosted`, and
 * this deployment's CI goes red until `/legal` names it — which is what the
 * old README test did, without meaning to (2026-09-30).
 *
 * Two keys the literal sweep cannot see are added around it: `STALE_CHUNK_KEY`
 * reaches storage through a parameter (`utils/reloadOnStaleChunk.js`), and
 * `i18nextLng` is written by `i18next-browser-languagedetector` under its own
 * default key — the note in `src/test/browserStorage.test.jsx` (~l. 47)
 * explains why a grep of this app's source is blind to it. It is also
 * re-written (same value it just read) by `useCollectionLanguage`'s
 * restore-cache, through a variable for the same reason.
 *
 * Each key is pinned to a phrase, not to bare presence, because the paragraph
 * says what a key is *for*; and the phrase is searched only inside the cookies
 * sentence because words like "language" appear elsewhere in the text.
 */

/** The same sweep as `src/test/browserStorage.test.jsx`, plus skipping
 * `src/test` itself: its helpers legitimately write throwaway keys. */
function sourceFiles(dir, found = []) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (full !== path.join('src', 'test')) sourceFiles(full, found);
    } else if (/\.(jsx|js)$/.test(entry.name) && !entry.name.includes('.test.')) found.push(full);
  }
  return found;
}

function storageKeys(source, method) {
  const pattern = new RegExp(`${method}\\.setItem\\(\\s*'([^']+)'`, 'g');
  return [...source.matchAll(pattern)].map((m) => m[1]);
}

// key → what the cookies sentence of each language calls it. Phrases from the
// current /legal (e29afaf2, checked against the text 2026-10-02).
const PHRASES = {
  userCode: { es: 'código de usuario', ca: "codi d'usuari", en: 'user code' },
  i18nextLng: { es: 'idioma', ca: 'idioma', en: 'language' },
  theeemeColors: { es: 'aspecto', ca: 'aspecte', en: 'appearance' },
  koro: { es: 'aspecto', ca: 'aspecte', en: 'appearance' },
  [STALE_CHUNK_KEY]: {
    es: 'recarga automática',
    ca: 'recàrrega automàtica',
    en: 'automatic reload',
  },
};

const COOKIE_SENTENCE = {
  es: '**Cookies y almacenamiento local:**',
  ca: '**Galetes i emmagatzematge local:**',
  en: '**Cookies and local storage:**',
};

/** The cookies sentence runs from its bold marker to the end of that line. */
function cookiesParagraph(text, marker) {
  const line = text.split('\n').find((l) => l.includes(marker));
  return line ? line.slice(line.indexOf(marker) + marker.length) : '';
}

describe('the /legal cookies sentence names every key the app stores (hosted)', () => {
  test('every key the app writes has a row in the table', () => {
    // Vitest runs from the frontend root, so `src` resolves; a wrong cwd
    // throws here rather than quietly sweeping nothing.
    const files = sourceFiles('src');
    expect(files.length).toBeGreaterThan(20);

    const scanned = new Set();
    for (const file of files) {
      const source = fs.readFileSync(file, 'utf8');
      for (const key of storageKeys(source, 'localStorage')) scanned.add(key);
    }
    expect(scanned.size).toBeGreaterThanOrEqual(3);

    for (const key of [...scanned, STALE_CHUNK_KEY, 'i18nextLng']) {
      expect(
        PHRASES,
        `new key \`${key}\`: name it in the /legal cookies sentence (all three languages) ` +
          'and add it to this table'
      ).toHaveProperty(key);
    }
  });

  test.each([
    ['es', es],
    ['ca', ca],
    ['en', en],
  ])('%s: every phrase in the table is in its cookies sentence', (lang, text) => {
    const paragraph = cookiesParagraph(text, COOKIE_SENTENCE[lang]);
    expect(paragraph, `${lang} /legal lost its cookies sentence`).not.toBe('');

    for (const [key, phrases] of Object.entries(PHRASES)) {
      expect(
        paragraph,
        `${lang} /legal does not name \`${key}\` in its cookies sentence`
      ).toContain(phrases[lang]);
    }
  });
});

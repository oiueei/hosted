import { describe, test, expect } from 'vitest';
import { readFileSync, readdirSync } from 'node:fs';
import path from 'node:path';
import hdsLang from './hdsLang';
import { SUPPORTED_LANGUAGES } from '../i18n';

/**
 * The one place that decides what language an HDS component announces itself in.
 * Six call sites depend on it (ImageUpload, GalleryUpload, PdfUpload, BulkAddCsv,
 * BulkInviteCsv, ShareCollectionMenu), and it had no test while
 * ShareCollectionMenu quietly carried a seventh, divergent copy.
 *
 * What it protects is the bug behind "Stop fourteen selects announcing
 * themselves in Finnish": HDS defaults to Finnish, so a call site that forgets
 * this mapping reads out its placeholders in a language nobody here speaks.
 */
describe('hdsLang', () => {
  test('the languages HDS ships strings for are passed straight through', () => {
    expect(hdsLang('fi')).toBe('fi');
    expect(hdsLang('sv')).toBe('sv');
  });

  test.each(SUPPORTED_LANGUAGES.map((l) => l.code))(
    'the app language %s resolves to a language HDS knows',
    (code) => {
      // Every language OIUEEI actually offers must come out as something HDS
      // understands, or that language's users get Finnish placeholders.
      expect(['fi', 'sv', 'en']).toContain(hdsLang(code));
    }
  );

  test('Spanish and Catalan fall back to English, not to the HDS default', () => {
    // The specific fallback matters: returning undefined (or nothing) hands the
    // component back to its Finnish default, which is the bug this exists for.
    expect(hdsLang('es')).toBe('en');
    expect(hdsLang('ca')).toBe('en');
  });

  test('a region-tagged or unknown code still resolves to English', () => {
    // i18next can hand over `es-ES` or `pt-BR`.
    expect(hdsLang('es-ES')).toBe('en');
    expect(hdsLang('pt-BR')).toBe('en');
    expect(hdsLang('de')).toBe('en');
    // Region-tagged Finnish included, and this pair is the point: the match has
    // to be exact. Written as `startsWith`, this would hand HDS the string
    // `fi-FI`, which is not one of the locales it ships — so the component falls
    // back to its own default and the passthrough achieves nothing. `load:
    // 'currentOnly'` means our own languages always arrive bare, so English is
    // the right answer for a tagged code rather than a guess at the base.
    expect(hdsLang('fi-FI')).toBe('en');
    expect(hdsLang('sv-SE')).toBe('en');
  });

  test('a missing language is answered, not passed on', () => {
    // `i18n.language` is undefined for the first paint of a fresh session, and
    // handing undefined to HDS is what makes it fall back to Finnish.
    expect(hdsLang(undefined)).toBe('en');
    expect(hdsLang('')).toBe('en');
  });
});

function jsxFiles(dir, acc = []) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) jsxFiles(full, acc);
    else if (/\.jsx?$/.test(entry.name) && !entry.name.includes('.test.')) acc.push(full);
  }
  return acc;
}

/**
 * No HDS `language` prop or `texts.language` should ever be a hardcoded
 * literal — every one of them must be routed through this file, or that call
 * site quietly stops following the app's own language (found in review,
 * 2026-09-18: seven `DateInput`/`Accordion` call sites had done exactly this,
 * hardcoding `"en"` instead of calling `hdsLang(i18n.language)` like every
 * other HDS component here already did).
 */
describe('every HDS `language` is routed through hdsLang', () => {
  test('no call site hardcodes a language literal', () => {
    const offenders = [];
    for (const file of jsxFiles('src')) {
      const source = readFileSync(file, 'utf8');
      // `language="en"` / `language='fi'` (a JSX attribute) and `language:
      // 'sv'` (a `texts` object key) are the two shapes every real call site
      // uses — `hdsLang(...)` is what belongs in either spot instead.
      for (const m of source.matchAll(/language\s*[:=]\s*['"](en|fi|sv)['"]/g)) {
        offenders.push(`${file}:${source.slice(0, m.index).split('\n').length}`);
      }
    }
    expect(offenders).toEqual([]);
  });

  test('the sweep is looking at a real tree, not an empty one', () => {
    const withHdsLang = jsxFiles('src').filter((f) => readFileSync(f, 'utf8').includes('hdsLang('));
    expect(withHdsLang.length).toBeGreaterThan(8);
  });
});

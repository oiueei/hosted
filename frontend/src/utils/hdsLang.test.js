import { describe, test, expect } from 'vitest';
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

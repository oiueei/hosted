import { describe, test, expect } from 'vitest';
import es from './es';
import ca from './ca';
import en from './en';

// The legal text is per-language content, not i18n keys — this is its parity
// guard, the analogue of i18nParity for `src/legal/`. `en` is the reference,
// as it is everywhere else in this repo.
//
// It checks structure, never wording: wording is exactly what a translation is
// allowed to change. What a translation must NOT change is how many sections a
// reader gets, in what order, and whether each one actually says something.
// Counting `# ` lines cannot see the failure that matters — a translation that
// keeps all five headings and empties one body reads as a complete document and
// still leaves that language's reader without a privacy notice.

const LANGS = { es, ca, en };
const CODES = Object.keys(LANGS);

/** A section is a `# ` heading plus everything up to the next one. */
function sections(text) {
  const out = [];
  for (const line of text.split('\n')) {
    if (line.startsWith('# ')) out.push({ heading: line.slice(2).trim(), body: '' });
    else if (out.length) out[out.length - 1].body += `${line}\n`;
  }
  return out.map((s) => ({ ...s, prose: s.body.replace(/\s+/g, ' ').trim() }));
}

describe('legal content parity', () => {
  const reference = sections(en);

  test('the reference text is a document, not a stub', () => {
    // Commitment, operator identity, privacy, terms, self-hosting — the five
    // the standalone ships. A sixth is fine; four means one went missing.
    expect(reference.length).toBeGreaterThanOrEqual(5);
  });

  test.each(CODES)('%s ships every section the reference does', (lang) => {
    const got = sections(LANGS[lang]).map((s) => s.heading);
    expect(got, `${lang} has ${got.length} sections, en has ${reference.length}`).toHaveLength(
      reference.length
    );
  });

  test.each(CODES)('%s gives every section a body, not just a heading', (lang) => {
    for (const [i, section] of sections(LANGS[lang]).entries()) {
      expect(section.heading, `${lang} section ${i + 1} has an empty heading`).not.toBe('');
      expect(
        section.prose.length,
        `${lang} section ${i + 1} ("${section.heading}") has no body — a reader of this ` +
          'language would get the heading and nothing under it'
      ).toBeGreaterThan(40);
    }
  });

  // Sections are matched by position, so a reordered translation would file its
  // privacy text where another language keeps its terms. Length is the only
  // cross-language comparison possible without comparing wording: these are
  // translations of one text, so the n-th section must be recognisably the same
  // section. The band is deliberately wide — it catches a swap or a gutting,
  // not the ordinary elasticity of translation.
  test.each(CODES.filter((c) => c !== 'en'))('%s keeps the sections in the same order', (lang) => {
    for (const [i, section] of sections(LANGS[lang]).entries()) {
      const ratio = section.prose.length / reference[i].prose.length;
      expect(
        ratio,
        `${lang} section ${i + 1} ("${section.heading}") is ${ratio.toFixed(1)}× the length of ` +
          `en's "${reference[i].heading}" — a section is missing, gutted, or out of order`
      ).toBeGreaterThan(1 / 3);
      expect(ratio).toBeLessThan(3);
    }
  });
});

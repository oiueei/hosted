import { describe, test, expect } from 'vitest';
import es from '../legal/es';
import ca from '../legal/ca';
import en from '../legal/en';

/**
 * What `/legal` says about the request-access page: that it counts, and counts only
 * numbers. The page keeps a counter per section and per press of "Request access"
 * (`hosted.models.AccessInterest`: a day, a need, a metric, a number), and a counter
 * the privacy text did not mention would be a claim the page makes about itself that
 * the text does not. Each language names it right after what is counted by device —
 * the other paragraph of the same kind — and says the two things that make it
 * harmless: no one, and no place.
 */

const TEXTS = {
  en: {
    text: en,
    lead: '**On the request-access page (numbers only):**',
    device: '**What we count (numbers only):**',
    harmless: /Not who, and not from where\./,
  },
  es: {
    text: es,
    lead: '**En la página de pedir acceso (solo números):**',
    device: '**Lo que contamos (solo números):**',
    harmless: /Ni quién, ni desde dónde\./,
  },
  ca: {
    text: ca,
    lead: '**A la pàgina de demanar accés (només números):**',
    device: '**El que comptem (només números):**',
    harmless: /Ni qui, ni des d'on\./,
  },
};

const paragraphs = (text) => text.split('\n\n').map((p) => p.trim());

describe('/legal and the request-access page', () => {
  test.each(Object.keys(TEXTS))('%s says what the page counts, in numbers only', (lang) => {
    const { text, lead, harmless } = TEXTS[lang];
    const found = paragraphs(text).filter((p) => p.startsWith(lead));

    expect(found, `${lang} must name the counters of the request-access page once`).toHaveLength(1);
    expect(found[0]).toMatch(harmless);
  });

  test.each(Object.keys(TEXTS))('%s puts it right after what is counted by device', (lang) => {
    const { text, lead, device } = TEXTS[lang];
    const all = paragraphs(text);
    const at = all.findIndex((p) => p.startsWith(lead));

    expect(at).toBeGreaterThan(0);
    expect(all[at - 1].startsWith(device)).toBe(true);
  });

  test('the sections named are the four the page has', () => {
    for (const { text, lead } of Object.values(TEXTS)) {
      const paragraph = paragraphs(text).find((p) => p.startsWith(lead));
      expect(paragraph).not.toMatch(/\bemail\b|\bIP\b/i);
    }
  });
});

import { describe, test, expect } from 'vitest';
import en from '../i18n/locales/en.json';
import es from '../i18n/locales/es.json';
import ca from '../i18n/locales/ca.json';

// Flatten an i18n resource object to its set of dotted leaf-key paths so two
// locales can be compared regardless of object ordering.
function keyPaths(obj, prefix = '') {
  const paths = [];
  for (const [key, value] of Object.entries(obj)) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      paths.push(...keyPaths(value, path));
    } else {
      paths.push(path);
    }
  }
  return paths;
}

const reference = new Set(keyPaths(en));
const locales = { es, ca };

// Every page title reads "{page} — OIUEEI" so a tab, a bookmark and a history
// entry say whose page it is. `titles.reserveThing` was the one that forgot, in
// all three languages, and nothing noticed because a title is only ever seen in
// a browser tab.
describe('page titles', () => {
  for (const [name, data] of Object.entries({ en, ...locales })) {
    test(`every ${name} title ends with the site name`, () => {
      const without = Object.entries(data.titles)
        .filter(([, title]) => !title.endsWith(' — OIUEEI'))
        .map(([key]) => key);
      expect(without).toEqual([]);
    });
  }
});

describe('i18n key parity', () => {
  test('en is the reference and is non-empty', () => {
    expect(reference.size).toBeGreaterThan(0);
  });

  for (const [name, data] of Object.entries(locales)) {
    test(`${name} has exactly the same keys as en (no missing, no extra)`, () => {
      const keys = new Set(keyPaths(data));
      const missing = [...reference].filter((k) => !keys.has(k));
      const extra = [...keys].filter((k) => !reference.has(k));
      expect({ missing, extra }).toEqual({ missing: [], extra: [] });
    });
  }
});

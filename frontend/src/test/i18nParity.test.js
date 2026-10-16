import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
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

// ── Every key is read ──────────────────────────────────────────────────────
// The parity test keeps the locales equal to each other and `i18nKeysExist` keeps
// the code to the catalogue; this is the third side: a key nothing reads is
// translated three times and maintained for nobody.
function sourceFiles(dir, found = []) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name !== 'test' && entry.name !== 'locales') sourceFiles(full, found);
    } else if (/\.(jsx|js)$/.test(entry.name) && !entry.name.includes('.test.')) {
      found.push(full);
    }
  }
  return found;
}

// Namespaces read through a variable prefix the sweep cannot follow, each with who
// reads them and how. Keep it this short.
const READ_THROUGH_A_VARIABLE = [
  // `MagicLinkJoinPage` builds every key as `${ns}.emailLabel`, `${ns}.join`… from
  // its `ns` prop, which the two join pages set to `share`.
  'share.',
];

const PLURAL_SUFFIX = /_(zero|one|two|few|many|other)$/;

describe('every key of en.json is read somewhere', () => {
  const source = sourceFiles('src')
    .map((file) => readFileSync(file, 'utf8'))
    .join('\n');

  const isRead = (rawKey) => {
    const key = rawKey.replace(PLURAL_SUFFIX, '');
    if (READ_THROUGH_A_VARIABLE.some((prefix) => key.startsWith(prefix))) return true;
    // Named whole, between quotes or backticks.
    if (new RegExp(`['"\`]${key.replace(/\./g, '\\.')}['"\`]`).test(source)) return true;
    // Or completed at runtime: `types.${v}` or 'types.' + v, for `types.GIFT_THING`.
    const parts = key.split('.');
    for (let i = 1; i < parts.length; i += 1) {
      const prefix = `${parts.slice(0, i).join('.')}.`.replace(/\./g, '\\.');
      if (new RegExp(`['"\`]${prefix}(\\$\\{|['"\`]\\s*\\+)`).test(source)) return true;
    }
    return false;
  };

  test('nothing is translated that no screen can show', () => {
    expect([...reference].filter((key) => !isRead(key))).toEqual([]);
  });

  test('a key nothing reads is told apart from one that is', () => {
    expect(isRead('common.connectionError')).toBe(true);
    expect(isRead('types.GIFT_THING')).toBe(true);
    expect(isRead('common.aKeyNoCodeNames')).toBe(false);
  });
});

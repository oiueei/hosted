import { describe, test, expect } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';
import en from '../i18n/locales/en.json';
import { deploymentI18n } from '../deployment';

/**
 * Every literal i18n key the code names exists in the catalogues.
 *
 * `i18nParity.test.js` holds the three locales to each other, but nothing
 * held the *code* to them: a `t('home.fooBody')` for a key nobody ever wrote
 * renders as the raw key on screen — "home.fooBody" — with every suite green,
 * because the parity test only compares the catalogues with each other. This
 * sweeps the source for the literal keys (`t('…')`, `i18n.t('…')` and
 * `<Trans i18nKey="…">`) and demands each one exists in `en.json` (merged with
 * whatever this deployment adds through `deploymentI18n`, which is `{}`
 * upstream and real pages on a deployment — without the merge, a deployment's
 * own keys would fail a sweep that runs in its CI too).
 *
 * Not extracted, on purpose:
 *  - keys built dynamically (`t('types.' + v)` and the backtipped
 *    `` t(`koro.${x}`) ``) — only a full, literal key is checkable;
 *  - prefixes ending in `.` — the fragment the code completes at runtime;
 *  - plurals resolve to `_one`/`_other` forms, which count as existing;
 *  - the whitelisted prefixes below, each with its reason.
 *
 * The floor (`> 1000`) is against the empty sweep: a regex that quietly
 * stopped matching (a lookbehind typo, a renamed import) would otherwise
 * pass forever having checked nothing — same shape as themedButtons.test.js.
 */

// `demoNotice.` — the one namespace a deployment owns outright. Upstream ships
// no such strings and `DemoNotice.jsx` asks `i18n.exists('demoNotice.body')`
// before rendering anything, so the literals name keys only a deployment can
// provide. On a deployment that supplies them they exist anyway.
const WHITELISTED_PREFIXES = ['demoNotice.'];

// The sweep measured 1164 literal key occurrences in `development` on 2026-09-30
// (1173 in `hosted`, whose deployment pages name their own). Three digits of
// slack: the floor is against emptiness, not against growth or a small prune.
const MINIMUM_KEYS_EXAMINED = 1000;

function sourceFiles(dir, found = []) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    // `src/test/` is fixtures and mocks, not product code.
    if (entry.isDirectory()) {
      if (entry.name !== 'test') sourceFiles(full, found);
    } else if (/\.(jsx|js)$/.test(entry.name) && !entry.name.includes('.test.')) found.push(full);
  }
  return found;
}

function flattenKeys(value, prefix = '', out = new Set()) {
  for (const [key, nested] of Object.entries(value)) {
    const dotted = prefix ? `${prefix}.${key}` : key;
    if (nested && typeof nested === 'object' && !Array.isArray(nested)) {
      flattenKeys(nested, dotted, out);
    } else {
      out.add(dotted);
    }
  }
  return out;
}

function deepMerge(base, extra) {
  const out = { ...base };
  for (const [key, value] of Object.entries(extra || {})) {
    out[key] =
      value && typeof value === 'object' && !Array.isArray(value)
        ? deepMerge(out[key] ?? {}, value)
        : value;
  }
  return out;
}

// `t('a.b')` / `i18n.t('a.b')`, single or double quoted. The lookbehind keeps
// any identifier ending in `t` out (`split(`, `toast(`, `toHaveBeenCalledWith(`):
// a translation `t` is either bare or preceded by a dot.
const T_CALL = /(?<![A-Za-z0-9_])t\(\s*(['"])([^'"\n]+)\1/g;
// `<Trans i18nKey="a.b">` — react-i18next's own attribute.
const I18N_KEY_ATTR = /\bi18nKey\s*=\s*(['"])([^'"\n]+)\1/g;

function literalKeys(source) {
  return [...source.matchAll(T_CALL), ...source.matchAll(I18N_KEY_ATTR)].map((m) => m[2]);
}

describe('every literal i18n key the code names exists', () => {
  test('no screen can end up showing a raw key', () => {
    const files = sourceFiles('src');
    expect(files.length).toBeGreaterThan(20);

    const catalogue = flattenKeys(deepMerge(en, deploymentI18n?.en));
    // i18next resolves `t(key, { count })` to the key's `_one`/`_other` forms.
    const exists = (key) =>
      catalogue.has(key) || catalogue.has(`${key}_one`) || catalogue.has(`${key}_other`);

    let examined = 0;
    const missing = [];
    for (const file of files) {
      for (const key of literalKeys(fs.readFileSync(file, 'utf8'))) {
        examined += 1;
        if (!key.includes('.')) continue; // not a namespaced translation key
        if (key.endsWith('.')) continue; // prefix the code completes at runtime
        if (WHITELISTED_PREFIXES.some((p) => key.startsWith(p))) continue;
        if (!exists(key)) missing.push(`${path.join(...file.split(path.sep))}: ${key}`);
      }
    }

    expect(
      examined,
      'the sweep extracted suspiciously few keys — the regex, not the code, broke'
    ).toBeGreaterThan(MINIMUM_KEYS_EXAMINED);
    expect(missing).toEqual([]);
  });
});

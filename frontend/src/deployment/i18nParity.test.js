import { describe, test, expect } from 'vitest';
import { deploymentI18n } from './i18n';

// The deployment analogue of `src/test/i18nParity.test.js`. Upstream that file
// guards the three `locales/*.json`; this one guards this deployment's own
// bundle, which merges into the same namespace. Without it a string added to
// `en` only ships English to a Spanish or Catalan reader — silently, since the
// key still resolves (to the fallback). `demoNotice`, added in three languages
// at once, is the reason this test now exists.
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

const reference = new Set(keyPaths(deploymentI18n.en));

describe('deployment i18n key parity', () => {
  test('en is the reference and is non-empty', () => {
    expect(reference.size).toBeGreaterThan(0);
  });

  for (const name of ['es', 'ca']) {
    test(`${name} has exactly the same keys as en (no missing, no extra)`, () => {
      const keys = new Set(keyPaths(deploymentI18n[name]));
      const missing = [...reference].filter((k) => !keys.has(k));
      const extra = [...keys].filter((k) => !reference.has(k));
      expect({ missing, extra }).toEqual({ missing: [], extra: [] });
    });
  }

  test('the demo-notice banner has all three of its parts, in every language', () => {
    for (const lang of ['en', 'es', 'ca']) {
      const notice = deploymentI18n[lang].demoNotice;
      expect(notice?.title, `${lang}.demoNotice.title`).toBeTruthy();
      expect(notice?.body, `${lang}.demoNotice.body`).toBeTruthy();
      expect(notice?.realNote, `${lang}.demoNotice.realNote`).toBeTruthy();
    }
  });
});

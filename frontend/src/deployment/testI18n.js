import i18n from 'i18next';

import { deploymentI18n } from './i18n';

/**
 * Registers this deployment's copy with the test i18n instance.
 *
 * The shared test setup (`src/test/setup.js`) initialises i18next straight from
 * `i18n/locales/en.json`, bypassing `i18n/index.js` — which is where the real
 * app merges these bundles in. So a test rendering one of this deployment's
 * pages would otherwise assert against raw keys, and pass or fail for reasons
 * that have nothing to do with the page.
 *
 * Import it for its side effect, first thing, in any test that renders them.
 * Deep merge, overwriting: this deployment's copy is the more specific.
 */
Object.entries(deploymentI18n).forEach(([language, bundle]) => {
  i18n.addResourceBundle(language, 'translation', bundle, true, true);
});

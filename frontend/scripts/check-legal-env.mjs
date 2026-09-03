/**
 * Build-time guard for the templated legal notice — the one page where a wrong
 * value is a compliance problem, not a cosmetic one.
 *
 * It refuses `vite build` in two cases:
 *
 * 1. **An identity field was inlined.** `src/legal/{ca,en,es}.js` must carry the
 *    operator's name, tax ID and address as `import.meta.env.VITE_LEGAL_*`
 *    interpolations, never as literal text. If the files reference any of those
 *    vars but not all three, one was hardcoded back — the exact regression this
 *    templating exists to prevent, and one no literal-matching rule can catch
 *    across three languages.
 * 2. **A referenced var is unset.** Vite replaces a missing `import.meta.env`
 *    value with the string `undefined` and says nothing, so the notice would
 *    ship reading "**undefined** — NIF undefined".
 *
 * **Self-configuring:** the standalone repo's `legal/*.js` reference no
 * `VITE_LEGAL_` var, so both checks find nothing and this exits 0 —
 * `package.json` differs between the two repos but the script is inert in one.
 *
 * Check 2 is "is it set?", not "is it real": CI sets `VITE_LEGAL_*` to a
 * placeholder so the build is exercised, and production sets the true values.
 *
 * The three predicates are pure so `check-legal-env.test.js` can exercise the
 * decision without a filesystem or a real build.
 */

import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const LEGAL_DIR = join(dirname(fileURLToPath(import.meta.url)), '..', 'src', 'legal');

// The operator-identity fields the legal notice templates. All or nothing.
export const EXPECTED_LEGAL_ENV = ['VITE_LEGAL_ADDRESS', 'VITE_LEGAL_NIF', 'VITE_LEGAL_OPERATOR'];

/** Every `import.meta.env.VITE_LEGAL_*` name referenced across the given sources. */
export function requiredLegalEnv(sources) {
  const found = new Set();
  const pattern = /import\.meta\.env\.(VITE_LEGAL_[A-Z0-9_]+)/g;
  for (const source of sources) {
    for (const match of source.matchAll(pattern)) found.add(match[1]);
  }
  return [...found].sort();
}

/**
 * Expected identity fields the sources do NOT reference, when they reference at
 * least one `VITE_LEGAL_` var. Non-empty ⇒ a field was inlined as literal text.
 */
export function inlinedLegalIdentity(sources) {
  const referenced = requiredLegalEnv(sources);
  if (referenced.length === 0) return [];
  return EXPECTED_LEGAL_ENV.filter((name) => !referenced.includes(name));
}

/** Referenced vars missing or blank in `env`. Empty ⇒ the environment is fine. */
export function missingLegalEnv(sources, env) {
  return requiredLegalEnv(sources).filter((name) => !env[name] || !String(env[name]).trim());
}

function readLegalSources() {
  return readdirSync(LEGAL_DIR)
    .filter((name) => name.endsWith('.js') && !name.endsWith('.test.js'))
    .map((name) => readFileSync(join(LEGAL_DIR, name), 'utf8'));
}

// Run only as a script, not when imported by the test.
if (import.meta.url === pathToFileURL(process.argv[1]).href) {
  const sources = readLegalSources();
  const inlined = inlinedLegalIdentity(sources);
  const missing = missingLegalEnv(sources, process.env);

  if (inlined.length) {
    console.error(
      `check-legal-env: src/legal/ references some VITE_LEGAL_* vars but not ${inlined.join(', ')} ` +
        '— an operator-identity field looks hardcoded. It must be interpolated, not written in.'
    );
    process.exit(1);
  }
  if (missing.length) {
    console.error(
      `check-legal-env: src/legal/ needs ${missing.join(', ')} in the environment, ` +
        `but ${missing.length === 1 ? 'it is' : 'they are'} unset.\n` +
        'Set them (CI uses a placeholder; production the real identity) before building.'
    );
    process.exit(1);
  }
}

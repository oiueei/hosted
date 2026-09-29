import { describe, test, expect } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';

/**
 * In production Vite builds with `base: '/static/'` (vite.config.js) and rewrites
 * the URLs it can *see* — the ones in `index.html` and in CSS `url()`. A path
 * written as a literal inside JS is invisible to it, so `<a href="/cocina-ejemplo.zip">`
 * shipped as exactly that, fell through to the SPA's catch-all (`config/urls.py`) and
 * downloaded the app's own `index.html` under a `.zip` name. Everything looked right
 * in development, where the base is `/` and both spellings are the same URL.
 *
 * A component test cannot see it either: `BASE_URL` is `/` under vitest, so the
 * rendered `href` is identical with and without the fix. What can see it is the
 * source. This sweeps every non-test `.js`/`.jsx` under `src` for a string literal
 * (quote, double quote or backtick) that opens with `/` + the name of something that
 * lives in `public/` — the list is read from the directory, not typed, so a file
 * added there next month is covered without anyone remembering to add it here.
 *
 * The fix is `import.meta.env.BASE_URL` in front of the name; that keeps the literal
 * from starting with `/` and is what production rewrites to `/static/`. CSS is left
 * out on purpose: Vite does rewrite `url()`.
 */
function sourceFiles(dir, found = []) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      // `src/test` is helpers and fixtures for vitest — none of it is bundled.
      if (full !== path.join('src', 'test')) sourceFiles(full, found);
    } else if (/\.(jsx|js)$/.test(entry.name) && !entry.name.includes('.test.')) found.push(full);
  }
  return found;
}

const escapeRegExp = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

/** Every literal in `source` that opens with `/<name>` for one of `names`. */
function publicFileLiterals(source, names) {
  const alternatives = names.map(escapeRegExp).join('|');
  // The lookahead is the end of the name: a quote, a path separator or a query/hash —
  // so `/fonts/x.woff2` counts and `/fontsize` does not.
  const pattern = new RegExp(`['"\`]/(?:${alternatives})(?=['"\`/?#])`, 'g');
  return [...source.matchAll(pattern)].map((m) => m[0]);
}

describe('the detector', () => {
  const names = ['cocina-ejemplo.zip', 'fonts', 'manifest.webmanifest'];

  test('catches the literal in each of the three quote styles', () => {
    expect(publicFileLiterals(`<a href="/cocina-ejemplo.zip">`, names)).toEqual([
      '"/cocina-ejemplo.zip',
    ]);
    expect(publicFileLiterals(`const u = '/cocina-ejemplo.zip';`, names)).toEqual([
      "'/cocina-ejemplo.zip",
    ]);
    expect(publicFileLiterals('const u = `/cocina-ejemplo.zip?v=2`;', names)).toEqual([
      '`/cocina-ejemplo.zip',
    ]);
  });

  test('catches a directory of public/ used as a prefix', () => {
    expect(publicFileLiterals(`url('/fonts/curiosa/Curiosa-Variable.woff2')`, names)).toEqual([
      "'/fonts",
    ]);
  });

  test('lets the fixed spelling through: the literal no longer opens with a slash', () => {
    expect(
      publicFileLiterals('href={`${import.meta.env.BASE_URL}cocina-ejemplo.zip`}', names)
    ).toEqual([]);
  });

  test('does not mistake a longer name, a route or prose for a public file', () => {
    expect(publicFileLiterals(`'/fontsize'`, names)).toEqual([]);
    expect(publicFileLiterals(`'/cocina-ejemplo.zip.bak'`, names)).toEqual([]);
    expect(publicFileLiterals(`to="/collections/new"`, names)).toEqual([]);
    expect(publicFileLiterals('// see /cocina-ejemplo.zip for the sample', names)).toEqual([]);
  });
});

describe('what this app cites from public/', () => {
  // Dotfiles are the OS's (`.DS_Store`), never something the app serves.
  const publicNames = fs.readdirSync('public').filter((name) => !name.startsWith('.'));

  test('the directory is read, and the example ZIP is among what it finds', () => {
    // Vitest runs from the frontend root; a wrong cwd throws in `readdirSync` above
    // instead of sweeping nothing. This pins that the list is real, so the sweep
    // below cannot go quiet because `public/` came back empty.
    expect(publicNames).toContain('cocina-ejemplo.zip');
    expect(publicNames.length).toBeGreaterThan(5);
  });

  test('no JS names one of them with a leading slash — production would not rewrite it', () => {
    const files = sourceFiles('src');
    expect(files.length).toBeGreaterThan(20);

    const offenders = files.flatMap((file) =>
      publicFileLiterals(fs.readFileSync(file, 'utf8'), publicNames).map(
        (literal) => `${file}: ${literal}…`
      )
    );

    expect(offenders).toEqual([]);
  });
});

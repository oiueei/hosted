import { describe, test, expect } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';
import { STALE_CHUNK_KEY } from '../utils/reloadOnStaleChunk';

/**
 * LSSI-CE art. 22.2 covers every device that stores and retrieves information
 * on the visitor's equipment — not just cookies: localStorage, sessionStorage
 * and IndexedDB all count. The README publishes "there is no banner because
 * everything here is strictly necessary" as a checkable claim, and a claim
 * like that is only honest for as long as something breaks the moment it
 * stops being true.
 *
 * This sweeps every `.jsx`/`.js` file under `src` (skipping tests, which
 * legitimately write throwaway keys) for `localStorage.setItem(` /
 * `sessionStorage.setItem(` calls and pins the exact set of keys written.
 * A new key lands here unnoticed otherwise: nothing else in CI reads
 * localStorage, and a key that started tracking something non-essential would
 * look, from the outside, identical to one of the three below.
 *
 * Inventory as of 2026-09-07 (README §Privacy carries the dated copy):
 *   - `userCode`     — which account is signed in, session bookkeeping
 *   - `theeemeColors`, `koro` — the signed-in user's own display preferences
 * All three are strictly necessary (session state or the visitor's own
 * preference, nothing observed about them) and none needs consent.
 *
 * `sessionStorage` holds **one** key since 2026-09-29: `staleChunkReloadAt`, the
 * time of the last automatic reload after a deploy left a tab asking for a chunk
 * that no longer exists (`utils/reloadOnStaleChunk.js` — the anti-loop mark). It
 * used to be "unused entirely". That module reaches storage through a parameter,
 * so a sweep for the literal `sessionStorage.setItem(` could not see it (and would
 * have kept passing had the write been added under an alias) — the check below is
 * therefore by *file*: any other source file that mentions `sessionStorage` is a new
 * decision, and the key itself has to be the one README §Privacy names.
 *
 * **Not swept, and real**: `i18next-browser-languagedetector` caches the
 * chosen UI language under its own default key, `i18nextLng` (see
 * `src/i18n/index.js`'s `detection: { caches: ['localStorage'] }`) — a
 * dependency's own write, invisible to a grep of this app's source, and
 * itself session preference rather than anything observed about the visitor.
 */
function sourceFiles(dir, found = []) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) sourceFiles(full, found);
    else if (/\.(jsx|js)$/.test(entry.name) && !entry.name.includes('.test.')) found.push(full);
  }
  return found;
}

const EXPECTED_LOCAL_STORAGE_KEYS = new Set(['userCode', 'theeemeColors', 'koro']);

function storageKeys(source, method) {
  const pattern = new RegExp(`${method}\\.setItem\\(\\s*'([^']+)'`, 'g');
  return [...source.matchAll(pattern)].map((m) => m[1]);
}

describe('what this app writes to the browser (LSSI-CE art. 22.2)', () => {
  test('every localStorage key written by app code is one of the three known ones', () => {
    // Vitest runs from the frontend root, so `src` resolves; a wrong cwd
    // throws here rather than quietly sweeping nothing.
    const files = sourceFiles('src');
    expect(files.length).toBeGreaterThan(20);

    const found = new Set();
    for (const file of files) {
      const source = fs.readFileSync(file, 'utf8');
      for (const key of storageKeys(source, 'localStorage')) found.add(key);
    }

    expect(found).toEqual(EXPECTED_LOCAL_STORAGE_KEYS);
  });

  test('sessionStorage is used by one module only, for the one key README names', () => {
    // Comments are stripped: prose about `sessionStorage` is not a use of it.
    const withoutComments = (source) =>
      source.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/.*$/gm, '');
    const files = sourceFiles('src');
    const users = files.filter((file) =>
      /\bsessionStorage\b/.test(withoutComments(fs.readFileSync(file, 'utf8')))
    );

    expect(users).toEqual([path.join('src', 'utils', 'reloadOnStaleChunk.js')]);
    expect(STALE_CHUNK_KEY).toBe('staleChunkReloadAt');

    // The claim is public (README §Privacy): the key must be in it, and the old
    // "unused" sentence must not be.
    const readme = fs.readFileSync('../README.md', 'utf8');
    expect(readme).toContain(`\`${STALE_CHUNK_KEY}\``);
    expect(readme).not.toContain('`sessionStorage` is unused');
  });
});

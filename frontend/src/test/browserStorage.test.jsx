import { describe, test, expect } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';

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
 * look, from the outside, identical to one of the four below.
 *
 * Inventory as of 2026-08-21 (README §Privacy carries the dated copy):
 *   - `userCode`     — which account is signed in, session bookkeeping
 *   - `theeemeColors`, `koro` — the signed-in user's own display preferences
 *   - `seenWelcome`  — whether the first-visit welcome box has been shown
 * All four are strictly necessary (session state or the visitor's own
 * preference, nothing observed about them) and none needs consent.
 *
 * `sessionStorage` is unused entirely — asserted below by the absence of any
 * `sessionStorage.setItem` call, not by its omission from a list.
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

const EXPECTED_LOCAL_STORAGE_KEYS = new Set(['userCode', 'theeemeColors', 'koro', 'seenWelcome']);

function storageKeys(source, method) {
  const pattern = new RegExp(`${method}\\.setItem\\(\\s*'([^']+)'`, 'g');
  return [...source.matchAll(pattern)].map((m) => m[1]);
}

describe('what this app writes to the browser (LSSI-CE art. 22.2)', () => {
  test('every localStorage key written by app code is one of the four known ones', () => {
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

  test('sessionStorage is never written', () => {
    const files = sourceFiles('src');
    const offenders = files.filter(
      (file) => storageKeys(fs.readFileSync(file, 'utf8'), 'sessionStorage').length > 0
    );

    expect(offenders).toEqual([]);
  });
});

/**
 * Keys this app used to keep in the browser and no longer reads.
 *
 * `theeemeColors` and `koro` held the signed-in person's palette and Koros wave: the
 * palette now belongs to a collection (or is the app's own, served in the page), so
 * a browser that still has them carries two stale preferences nobody uses. They are
 * removed once, at start-up, so the inventory in the README (§ Privacy) is true of
 * browsers that have visited before too.
 *
 * TODO: drop this a few releases after it ships, when no browser can still have them.
 */
export const RETIRED_KEYS = ['theeemeColors', 'koro'];

export function forgetRetiredPreferences() {
  for (const key of RETIRED_KEYS) {
    try {
      localStorage.removeItem(key);
    } catch {
      // Storage can be unavailable (private mode, blocked site data); nothing to clean.
    }
  }
}

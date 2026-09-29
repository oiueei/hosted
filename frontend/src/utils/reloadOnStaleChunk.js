/**
 * Recover a tab that was open across a deploy.
 *
 * Every page is `lazy()`-loaded from a chunk with a content hash in its name, and a
 * Heroku release ships only the new chunks (WhiteNoise serves what `collectstatic`
 * copied from `frontend/dist`). A tab opened before the deploy still holds the old
 * `index-*.js`, so the first navigation to a page it had not loaded asks for a chunk
 * that no longer exists. `lazy()` rethrows and the top-level `ErrorBoundary` swaps
 * the whole app for "Something went wrong" — for a page that was fine a minute ago.
 *
 * Vite dispatches a cancelable `vite:preloadError` on `window` when a dynamic import
 * fails. Reloading fetches the current `index.html` and with it the current chunk
 * names, which is the whole cure. Preventing the default keeps the error from being
 * thrown at all.
 *
 * **One reload per window, never a loop.** If the chunk is still missing after the
 * reload (a broken release, a stale cache in front of `index.html`) the error comes
 * back at once, and reloading again would spin forever. So the time of the last
 * reload is kept in `sessionStorage` — it lives as long as the tab and nothing else
 * reads it — and a second failure inside `RELOAD_WINDOW_MS` is left alone, to reach
 * the `ErrorBoundary` as it did before this existed. That guard is the reason the
 * mark exists: **when it cannot be read or written (storage blocked, quota, private
 * mode) the reload is skipped too**, because reloading without being able to
 * remember it is exactly the loop being avoided.
 *
 * The one key is part of the published browser-storage inventory (README §Privacy);
 * `test/browserStorage.test.jsx` pins both.
 */
export const STALE_CHUNK_KEY = 'staleChunkReloadAt';
export const RELOAD_WINDOW_MS = 10_000;

/** `win.sessionStorage`, or `null` when merely touching it throws (SecurityError). */
function sessionStorageOf(win) {
  try {
    return win.sessionStorage ?? null;
  } catch {
    return null;
  }
}

/**
 * Reloaded within the window? A stamp that is not a number counts as "not recently",
 * but a read that *throws* means we cannot tell whether we just reloaded — and the
 * only safe answer to that is yes.
 */
function reloadedRecently(store, now) {
  try {
    const at = Number(store.getItem(STALE_CHUNK_KEY));
    // A stamp in the future (a clock that moved back) is not "recent": it would
    // hold the guard shut until the clock caught up.
    return Number.isFinite(at) && now - at >= 0 && now - at < RELOAD_WINDOW_MS;
  } catch {
    return true;
  }
}

/** Did the mark land? A `false` means the caller must not reload. */
function markReload(store, now) {
  try {
    store.setItem(STALE_CHUNK_KEY, String(now));
    return true;
  } catch {
    return false;
  }
}

/**
 * Reload once when a lazy chunk has gone missing. `storage` defaults to the window's
 * own `sessionStorage`, looked up inside a try/catch (a bare default parameter would
 * throw here, before the app renders, in a browser that blocks storage). Returns the
 * function that uninstalls the listener.
 */
export function installStaleChunkReload(win = window, storage) {
  const onPreloadError = (event) => {
    const store = storage ?? sessionStorageOf(win);
    if (!store) return;
    const now = Date.now();
    if (reloadedRecently(store, now)) return;
    if (!markReload(store, now)) return;
    event.preventDefault();
    win.location.reload();
  };
  win.addEventListener('vite:preloadError', onPreloadError);
  return () => win.removeEventListener('vite:preloadError', onPreloadError);
}

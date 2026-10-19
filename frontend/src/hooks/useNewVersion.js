import { useEffect, useState } from 'react';

// How soon after a check the next one may run. A tab that goes in and out of view
// all day asks the server for the page once per window, not once per glance.
export const CHECK_EVERY_MS = 10 * 60 * 1000;

const ENTRY_SCRIPT = 'script[type="module"][src]';

// The address of the script that starts the app, as a document names it. Every
// build gives that file a name made from its content, so a different name is a
// different version.
function entryScript(doc) {
  return doc.querySelector(ENTRY_SCRIPT)?.getAttribute('src') || null;
}

/**
 * Whether the server now hands out a newer build than the one this tab is running.
 *
 * A tab opened before a release keeps its old texts and code until it is reloaded.
 * When it comes back into view (`visibilitychange`), at most once every
 * `CHECK_EVERY_MS`, this asks the server for the app's own front page (`/`, same
 * origin, no parameters and no headers of its own: the server already sends it
 * `no-cache`), reads the entry script out of it and compares it with the one the
 * page is running. It only reports; reloading is the reader's call, since a form
 * may be half written. A failed request, or a page it cannot read, says nothing.
 *
 * Production only: in development the entry is `/src/main.jsx` and never changes.
 * Nothing is stored in the browser — the time of the last check lives in memory.
 */
export default function useNewVersion() {
  const [available, setAvailable] = useState(false);

  useEffect(() => {
    if (!import.meta.env.PROD || available) return undefined;

    let lastCheck = -Infinity;
    let running = false;
    let cancelled = false;

    const check = async () => {
      running = true;
      lastCheck = Date.now();
      try {
        const res = await fetch('/');
        if (!res.ok) return;
        const served = entryScript(new DOMParser().parseFromString(await res.text(), 'text/html'));
        const mine = entryScript(document);
        if (!cancelled && served && mine && served !== mine) setAvailable(true);
      } catch {
        // Offline, or the server is busy: nothing to say, and the next window tries again.
      } finally {
        running = false;
      }
    };

    const onVisibility = () => {
      if (document.visibilityState !== 'visible' || running) return;
      if (Date.now() - lastCheck < CHECK_EVERY_MS) return;
      check();
    };

    document.addEventListener('visibilitychange', onVisibility);
    return () => {
      cancelled = true;
      document.removeEventListener('visibilitychange', onVisibility);
    };
  }, [available]);

  return available;
}

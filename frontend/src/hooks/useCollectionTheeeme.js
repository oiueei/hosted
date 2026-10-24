import { useLayoutEffect, useSyncExternalStore } from 'react';

/**
 * The palette a collection's pages are painted with — the other half of
 * `useTheeeme`.
 *
 * A page that belongs to a collection (its own page, a thing in it, its join door,
 * its forms) tells the app which colours and which Koros wave to wear with
 * `useCollectionTheeeme(colors, koro)`; `useTheeeme()` — read by the page, its hero,
 * its buttons, `PageLayout` — then answers with those, and with the app's own
 * palette whenever no collection page is mounted. The same spirit as
 * `useCollectionLanguage`.
 *
 * It is a small external store rather than a React context on purpose: any page can
 * declare its palette without every test, every route and every nested tree having
 * a provider above it, and it still re-renders its readers. (A context was the other
 * way to do it; this is the equivalent that needs no wrapper.)
 *
 * **The declaration happens in a layout effect**, so a page that already has its data
 * on its first render is repainted with its own colours before the browser draws a
 * frame: the app's palette is never seen for an instant. A page that fetches its
 * collection should not paint its hero before the response (the app's palette would
 * show until it lands), and says so by rendering a loading state until then.
 *
 * The declaration is withdrawn when the page unmounts, so leaving a collection for
 * Home puts the app's palette back at once.
 */
let current = null; // { colors: { color_01..color_06 }, koro } or null
const listeners = new Set();

function subscribe(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function snapshot() {
  return current;
}

function publish(next) {
  current = next;
  listeners.forEach((listener) => listener());
}

/** What is declared at this instant, outside React (a layout effect that must know). */
export function declaredNow() {
  return current;
}

/** The palette a collection page declared, or `null` when none is mounted. */
export function useDeclaredCollectionTheeeme() {
  return useSyncExternalStore(subscribe, snapshot, snapshot);
}

/**
 * Declare the palette of the collection this page belongs to.
 *
 * @param {object|null|undefined} colors `color_01`..`color_06` HDS token names, as the API serves
 *   them (`theeeme_colors`, `collection_theeeme_colors`). Nothing usable means no declaration
 *   (the page wears the app's palette).
 * @param {string} [koro] the Koros wave type (`koro`, `collection_koro`); `basic` when absent.
 */
export default function useCollectionTheeeme(colors, koro) {
  // Stringified for a stable dependency: a caller passes a fresh object every render.
  const key = colors && Object.keys(colors).length > 0 ? JSON.stringify(colors) : '';
  useLayoutEffect(() => {
    if (!key) return undefined;
    const mine = { colors: JSON.parse(key), koro: koro || 'basic' };
    publish(mine);
    return () => {
      // Only withdraw what is still ours: a page that mounted after this one has
      // already replaced it, and its declaration must survive our cleanup.
      if (current === mine) publish(null);
    };
  }, [key, koro]);
}

/**
 * Where a collection lives in the app: `/{kind}/{code}` — `/stall/AbC123`,
 * `/library/AbC123`, `/shed/AbC123`. The kind is fixed when a collection is
 * created, and every answer that names a collection for the app to link to
 * carries it (`collection.kind`, a thing's `collection_kind`, a notice's
 * `payload.collection_kind`, …).
 *
 * `/collections/{code}` is the address from before kinds. It still resolves — the
 * server answers it with a 301 to the right one and `useCanonicalCollectionPath`
 * moves a client-side visit there — so a link made without a kind (an answer from
 * an older server, a test fixture) is wrong only by a redirect, never dead.
 */
export const COLLECTION_KINDS = ['STALL', 'LIBRARY', 'SHED'];

// The prefixes a collection's pages are mounted under: one per kind, and the old
// one. `App.jsx` builds its route tree once from this list.
export const COLLECTION_PREFIXES = ['stall', 'library', 'shed', 'collections'];

const LEGACY_PREFIX = 'collections';

/** `stall` / `library` / `shed` for a kind, `collections` when there is none. */
export function kindSegment(kind) {
  return COLLECTION_KINDS.includes(kind) ? kind.toLowerCase() : LEGACY_PREFIX;
}

/** The route of a collection's page, or of one of its sub-pages (`rest` = `/edit`). */
export function collectionPath(code, kind, rest = '') {
  return `/${kindSegment(kind)}/${code}${rest}`;
}

/** The route of a thing inside a collection, or of one of its sub-pages. */
export function collectionThingPath(code, kind, thingCode, rest = '') {
  return collectionPath(code, kind, `/things/${thingCode}${rest}`);
}

/** The kind a prefix stands for, or `undefined` for `collections` and anything else. */
export function kindOfPrefix(prefix) {
  const kind = String(prefix || '').toUpperCase();
  return COLLECTION_KINDS.includes(kind) ? kind : undefined;
}

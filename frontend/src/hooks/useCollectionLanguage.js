import { useEffect, useState } from 'react';
import i18n, { SUPPORTED_LANGUAGES } from '../i18n';
import { loadUserLanguage } from './useCapabilities';

const STORAGE_KEY = 'i18nextLng';
const SUPPORTED_CODES = SUPPORTED_LANGUAGES.map((entry) => entry.code);

/**
 * Applies a collection's own language to a page's generic interface chrome —
 * "Join to take part", "Curator:", every plain i18n string around the owner's
 * own headline/description, which already renders in the collection's
 * language for anyone via `resolve_localized` (`utils/localized.js`)
 * regardless of who is looking.
 *
 * The hierarchy (CA, 2026-09-15, mirrors the email-side
 * `resolve_email_language`): a signed-in visitor's own deliberately-saved
 * profile language always wins; failing that, the language of the collection
 * they are looking at; failing that, today's plain browser/localStorage
 * default, unchanged. **This hook only ever implements the middle tier.** The
 * top tier — actually applying a real preference, not just deferring to it —
 * is `App.jsx`'s own `/auth/me/` warm-up effect, which runs once per visit,
 * ahead of any page; this hook's job on top of that is narrower: given that a
 * preference exists, stay out of its way.
 *
 * **The one rule that makes this safe**: the override this hook applies is
 * never written to the `i18nextLng` cache `i18next-browser-languagedetector`
 * reads back on the *next* page load. Doing that would silently stamp a
 * visitor's language exactly the way `JoinView` used to stamp `User.language`
 * (`core/views/auth.py`) — the collection they happened to land on first
 * would become their permanent default everywhere else too, outranking every
 * other collection's own language forever. So every `changeLanguage()` call
 * this hook makes — applying the override on mount, reverting it on unmount —
 * is immediately followed by putting the cache entry back exactly as found,
 * whether that was a real value or nothing at all. A visitor with a
 * deliberate preference of their own is left alone entirely: this hook never
 * calls `changeLanguage` for them.
 *
 * The restore itself runs **synchronously**, right after `changeLanguage` is
 * called, not chained onto its returned promise. `i18next`'s
 * `cacheUserLanguage()` (the write we are undoing) fires synchronously inside
 * `changeLanguage`, before that promise resolves — which for `es`/`ca` waits
 * on their lazy-loaded chunk (`i18n/index.js`). Restoring only in `.then()`
 * left the *wrong* value sitting in `localStorage` for the whole chunk
 * download, on precisely the first visit to a non-English collection: a
 * reload or a middle-click during that window would have read it back as a
 * deliberate choice (found in review, 2026-09-15). The `.then()` is kept
 * too, as a harmless no-op restore once the language has actually finished
 * loading, in case a future i18next version ever changes that ordering.
 *
 * `collectionLanguage` is the raw `language` field from a `Collection` or
 * `Thing` (`collection_language`) API response — `''`/`null`/an unsupported
 * code are all treated as "no collection language" and this hook does nothing.
 */
export default function useCollectionLanguage(collectionLanguage) {
  // null = not yet known. Resolved once per distinct collection language so a
  // page that never needs it (the common case: most collections set none)
  // never fetches `/auth/me/` at all.
  const [ownLanguage, setOwnLanguage] = useState(null);

  useEffect(() => {
    if (!collectionLanguage || !SUPPORTED_CODES.includes(collectionLanguage)) return undefined;
    let alive = true;
    loadUserLanguage().then((value) => {
      if (alive) setOwnLanguage(value || '');
    });
    return () => {
      alive = false;
    };
  }, [collectionLanguage]);

  useEffect(() => {
    if (!collectionLanguage || !SUPPORTED_CODES.includes(collectionLanguage)) return undefined;
    // Still waiting to hear whether this visitor has a preference of their
    // own — do nothing rather than flash the collection's language and then
    // possibly flash away again once the real answer lands.
    if (ownLanguage === null) return undefined;
    // A deliberate preference of their own always wins — this hook has
    // nothing to do.
    if (ownLanguage) return undefined;
    if (i18n.language === collectionLanguage) return undefined;

    const storedBefore = localStorage.getItem(STORAGE_KEY);
    const languageBefore = i18n.language;
    const restoreCache = () => {
      if (storedBefore === null) localStorage.removeItem(STORAGE_KEY);
      else localStorage.setItem(STORAGE_KEY, storedBefore);
    };

    const applied = i18n.changeLanguage(collectionLanguage);
    restoreCache();
    applied.then(restoreCache);
    return () => {
      const reverted = i18n.changeLanguage(languageBefore);
      restoreCache();
      reverted.then(restoreCache);
    };
  }, [collectionLanguage, ownLanguage]);
}

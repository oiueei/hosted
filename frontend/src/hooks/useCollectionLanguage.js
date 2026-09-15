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
 * default, unchanged.
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
    if (!collectionLanguage) return undefined;
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

    i18n.changeLanguage(collectionLanguage).then(restoreCache);
    return () => {
      i18n.changeLanguage(languageBefore).then(restoreCache);
    };
  }, [collectionLanguage, ownLanguage]);
}

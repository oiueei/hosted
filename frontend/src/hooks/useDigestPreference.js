import { useCallback, useRef, useState } from 'react';
import { apiFetch } from '../services/api';

/**
 * A member silences — or turns back on — the summary email of this one group
 * (`POST /api/v1/collections/{code}/digest/ {"muted": true|false}`, members only).
 * It used to be reachable only from the footer of the email itself
 * (`DigestMutePage`); the collection menu offers it now (X2, CA 2026-10-04), and
 * the page that unsubscribes already promises it: "you can turn it back on from
 * the collection page".
 *
 * `muted` is what the page knows (`is_digest_muted`); `onChange(next)` is how it
 * learns the answer, so the menu's wording follows the server's word and not a
 * guess made before it. The outcome is a message the page paints in a status zone
 * (`CollectionDigestStatus`), like the downloads': `result` is `{ type, key }`
 * with an i18n key — translated where it is painted, so it follows a language
 * change — or `null`. A ref, not `busy`, blocks a second press: two in one tick
 * both read the old state.
 */
export default function useDigestPreference({ code, muted, onChange }) {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const running = useRef(false);

  const toggle = useCallback(async () => {
    if (running.current) return;
    running.current = true;
    setBusy(true);
    setResult(null);
    const next = !muted;
    try {
      const res = await apiFetch(`/api/v1/collections/${code}/digest/`, {
        method: 'POST',
        body: JSON.stringify({ muted: next }),
      });
      if (res.ok) {
        onChange(next);
        setResult({
          type: 'success',
          key: next ? 'collectionMenu.digestMuted' : 'collectionMenu.digestUnmuted',
        });
      } else {
        setResult({
          type: 'error',
          key: res.status === 429 ? 'common.tooManyAttempts' : 'collectionMenu.digestError',
        });
      }
    } catch {
      setResult({ type: 'error', key: 'common.connectionError' });
    } finally {
      running.current = false;
      setBusy(false);
    }
  }, [code, muted, onChange]);

  return { muted, busy, result, toggle };
}

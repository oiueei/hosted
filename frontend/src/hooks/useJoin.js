import { useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { getCsrfToken } from '../services/api';

/**
 * The shared `/auth/join/` submit — how a visitor pointed at a collection joins
 * it and gets a magic link back.
 *
 * Its two callers render it very differently, which is why they stay separate
 * components: `MagicLinkJoinPage` is a boxed `PageLayout` page
 * (`/share/:token`), `JoinToAct` renders unboxed inside `JoinPage`'s hero and
 * reports errors inline. But the request itself — the CSRF header, the
 * `language` field, the 429 branch, the `seenWelcome` reset — was identical in
 * both, kept as two copies that had already drifted apart in one place.
 *
 * That drift was a re-entry guard only `JoinToAct` carried, and as written it
 * was decorative: it read the `loading` *state*, which a second submit in the
 * same tick still sees as `false`, because it runs the previous render's
 * closure. The guard here is a **ref**, which the second call does observe, so
 * it holds even when React has not re-rendered in between. In practice
 * `disabled={loading}` already covers the reachable cases — React flushes
 * discrete events synchronously, so the button is disabled before a second
 * click or an implicit Enter submit can land. This is the cheap belt to that
 * pair of braces, on a request whose side effect is an email to a stranger.
 *
 * Options: `sentMessageKey` / `errorMessageKey` (i18n keys — they differ per
 * door) and `extraBody` (merged into the POST: `JoinToAct`'s `collection_code`,
 * `SharePage`'s `share_token`).
 *
 * Returns `{ email, setEmail, loading, status, message, submit }`, where
 * `status` is `null` | `'success'` | `'error'` and `submit` is a form handler.
 */
export default function useJoin({ sentMessageKey, errorMessageKey, extraBody } = {}) {
  const { t, i18n } = useTranslation();
  const [email, setEmail] = useState('');
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState(null); // 'success' | 'error'
  const [message, setMessage] = useState('');
  // A ref, not the `loading` state: a second submit dispatched before React
  // re-renders runs this render's closure, where the state is still false.
  const inFlight = useRef(false);

  const submit = async (e) => {
    e.preventDefault();
    if (inFlight.current) return;
    inFlight.current = true;
    setStatus(null);
    setLoading(true);
    try {
      const res = await fetch('/api/v1/auth/join/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCsrfToken(),
        },
        // `language` is stored on a brand-new user, so their very first magic
        // link already speaks the language they're reading this page in.
        body: JSON.stringify({
          email,
          language: i18n.resolvedLanguage || i18n.language,
          ...extraBody,
        }),
      });
      if (res.ok) {
        localStorage.removeItem('seenWelcome');
        setStatus('success');
        setMessage(t(sentMessageKey));
      } else if (res.status === 429) {
        setStatus('error');
        setMessage(t('common.tooManyAttempts'));
      } else {
        setStatus('error');
        setMessage(t(errorMessageKey));
      }
    } catch {
      setStatus('error');
      setMessage(t('common.connectionError'));
    } finally {
      // Released on failure too, so a rate-limited or offline visitor can retry.
      inFlight.current = false;
      setLoading(false);
    }
  };

  return { email, setEmail, loading, status, message, submit };
}

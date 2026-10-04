import { useEffect, useState } from 'react';
import { apiFetch } from '../services/api';

/**
 * Whether "Requests to me" has anything to show this account: `receives_requests`
 * on `GET /auth/me/` — owns a thing, or founds or co-curates a PROPRIETARY
 * collection, which only the server knows. Shared by the two menus that can carry
 * the link (the account menu, and the collection menu on a collection's page and on
 * a thing's, X4, CA 2026-10-04), with one behaviour:
 *
 * - asked **when the panel opens** (`open` goes true), and again each time, so an
 *   account that has just got its first thing, or been made a curator, sees the link
 *   without a reload;
 * - nothing is kept in the browser for it (a new storage key is one more line in the
 *   `/legal`);
 * - **no answer, no link**: while the answer is not there, on an error status or a
 *   failed request, it is `false` — guessing would put a dead page back in the menu.
 */
export default function useReceivesRequests(open) {
  const [receives, setReceives] = useState(false);

  useEffect(() => {
    if (!open) return undefined;
    const controller = new AbortController();
    const { signal } = controller;
    const ask = async () => {
      try {
        const res = await apiFetch('/api/v1/auth/me/', { signal });
        if (!res.ok) return;
        const data = await res.json();
        if (!signal.aborted) setReceives(data.receives_requests === true);
      } catch {
        // No answer, no link.
      }
    };
    ask();
    return () => controller.abort();
  }, [open]);

  return receives;
}

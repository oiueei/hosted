import { useEffect, useState } from 'react';
import { apiFetch } from '../services/api';

/**
 * What this deployment lets the signed-in account create — the `capabilities`
 * block on `GET /auth/me/` (see `core/services/creator_policy.py`).
 *
 * Upstream OIUEEI answers "everything, and nowhere to ask", so every consumer
 * of this hook renders exactly what it rendered before the endpoint carried the
 * field. It matters on a deployment that withholds something: the forms stop
 * offering what the API would refuse, instead of letting someone fill a form in
 * and meet a 403 at the end of it.
 *
 * **Null until known, and null on failure.** Callers treat null as "no
 * restriction" and show the full catalogue — the same fail-open reasoning the
 * whole file rests on: this is a courtesy to the user, never the gate. The gate
 * is the server, which refuses regardless of what the browser managed to fetch.
 */

// One request per signed-in account, shared by every page that asks. The four
// forms that consume this are otherwise four extra calls to an endpoint the app
// already hits on load. Keyed by user so it cannot outlive a logout and answer
// for whoever signs in next.
let cached = { userCode: null, promise: null };

export function loadCapabilities() {
  const userCode = localStorage.getItem('userCode');
  if (cached.promise && cached.userCode === userCode) return cached.promise;

  const promise = apiFetch('/api/v1/auth/me/')
    .then((res) => (res.ok ? res.json() : null))
    .then((data) => data?.capabilities ?? null)
    .catch(() => null);

  cached = { userCode, promise };
  return promise;
}

export default function useCapabilities() {
  const [capabilities, setCapabilities] = useState(null);

  useEffect(() => {
    let alive = true;
    loadCapabilities().then((value) => {
      if (alive) setCapabilities(value);
    });
    return () => {
      alive = false;
    };
  }, []);

  return capabilities;
}

/**
 * Whether a form should offer `value` for `kind` — the filter behind every
 * shortened option list.
 *
 * Unknown capabilities offer everything: this is the fail-open half described
 * above, and it is also what makes the whole file a no-op upstream.
 *
 * `current` — the value being edited — is always offered even when the policy
 * no longer allows it. Someone editing a collection opened before this
 * deployment narrowed must still see which mode it is in, and saving it
 * unchanged has to keep working: the server only judges a *change*, so a form
 * that hid the current answer would show a wrong one and then submit it.
 */
export function isOfferable(capabilities, kind, value, current = null) {
  const allowed = capabilities?.[kind];
  if (!allowed) return true;
  return allowed.includes(value) || value === current;
}

/**
 * Centralised fetch wrapper with cookie-based auth and 401 handling.
 */

export function getCsrfToken() {
  const match = document.cookie.match(/csrftoken=([^;]+)/);
  return match ? match[1] : '';
}

// Single-flight token refresh: when several authenticated requests race on a
// just-expired access token they all get 401 at once. Without a shared promise
// each would POST its own /auth/refresh/, and with rotating refresh tokens the
// later ones present an already-rotated (blacklisted) token, fail, and log the
// user out mid-session. Funnel every concurrent 401 through one refresh.
let refreshPromise = null;

function refreshTokens() {
  if (!refreshPromise) {
    refreshPromise = fetch('/api/v1/auth/refresh/', {
      method: 'POST',
      credentials: 'include',
      headers: { 'X-CSRFToken': getCsrfToken() },
    }).finally(() => {
      // Clear once settled so a later expiry can refresh again.
      refreshPromise = null;
    });
  }
  // All awaiters share one Response — only read `.ok` here, never the body.
  return refreshPromise;
}

/**
 * Best user-facing message from a failed API response body.
 *
 * DRF sends `{detail}`, our views often use `{error}`, and serializer errors come
 * as `{non_field_errors: [...]}` or `{field: [...]}`. Returns the most specific
 * string, or `null` when there is no usable body — callers fall back to their own
 * i18n copy. A 429 has no useful body, so callers should map `res.status === 429`
 * to their own "too many attempts" message before calling this.
 */
export async function extractApiError(res) {
  try {
    const data = await res.json();
    if (!data) return null;
    if (typeof data === 'string') return data;
    if (data.detail) return data.detail;
    if (data.error) return data.error;
    if (Array.isArray(data.non_field_errors) && data.non_field_errors.length) {
      return String(data.non_field_errors[0]);
    }
    for (const value of Object.values(data)) {
      if (Array.isArray(value) && value.length) return String(value[0]);
      if (typeof value === 'string') return value;
    }
    return null;
  } catch {
    return null;
  }
}

/**
 * `optionalAuth: true` — for a page that renders for anonymous visitors but shows
 * a little more when there *is* a session (`/welcome`: the greeting, the example
 * collections). An unrecoverable 401 then returns the response so the caller can
 * shrug it off, instead of clearing `userCode` and hard-navigating to `/login`.
 *
 * Without it, one authenticated call on a public page evicts every anonymous
 * visitor: the redirect fires inside `apiFetch`, so a caller's `.catch()` runs
 * far too late to stop it — which is exactly what made the public `/welcome`
 * route unreachable without an account.
 *
 * The refresh attempt still runs, so a signed-in reader whose access token has
 * merely expired keeps their greeting rather than silently downgrading to the
 * anonymous view.
 */
export async function apiFetch(url, options = {}) {
  const { optionalAuth = false, ...fetchOptions } = options;
  const headers = { ...fetchOptions.headers };

  if (fetchOptions.body && !headers['Content-Type']) {
    headers['Content-Type'] = 'application/json';
  }

  const method = (fetchOptions.method || 'GET').toUpperCase();
  if (!['GET', 'HEAD', 'OPTIONS', 'TRACE'].includes(method) && !headers['X-CSRFToken']) {
    headers['X-CSRFToken'] = getCsrfToken();
  }

  const res = await fetch(url, { ...fetchOptions, headers, credentials: 'include' });

  if (res.status === 401) {
    // Try refreshing the token once (shared across concurrent 401s)
    const refreshRes = await refreshTokens();
    if (refreshRes.ok) {
      // Retry the original request with fresh cookies
      const retryRes = await fetch(url, { ...fetchOptions, headers, credentials: 'include' });
      if (retryRes.status === 401) {
        if (optionalAuth) return retryRes;
        localStorage.removeItem('userCode');
        window.location.href = '/login';
        throw new Error('Unauthorised');
      }
      return retryRes;
    }
    if (optionalAuth) return res;
    localStorage.removeItem('userCode');
    window.location.href = '/login';
    throw new Error('Unauthorised');
  }

  return res;
}

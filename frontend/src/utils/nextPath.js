/**
 * Where a login should send the person back to: a path on this site, nothing else.
 *
 * A session that ran out on a page used to send the reader to `/login` without
 * saying where they were going, so the magic link they asked for landed on their
 * one collection or on Home. The destination now travels in the URL of `/login`
 * (`?next=`), in the body of `request-link`, and back in the verify response.
 * It is deliberately **not** kept in browser storage: the link is often opened in
 * another browser (webmail, the phone's mail app), which shares none with the one
 * that showed `/login`, and the README's inventory of storage keys stays as is.
 *
 * `safeNextPath` is the same rule as `core.utils.safe_next_path` on the server —
 * *that* is the gate; this copy is defence in depth, and the two must not drift
 * (`nextPath.test.js` and `core/tests/unit/test_safe_next_path.py` share their
 * tables by hand). A value is accepted only when it is a string of at most 256
 * characters that matches the whitelist (no `\`, `#`, `:` or whitespace, so no
 * scheme and no backslash-as-slash), does not start with `//`, has no `..` (raw
 * or percent-decoded), is not `/` alone, and does not start at one of the SPA's
 * own doors — compared decoded and case-folded, because the router does both.
 */
const NEXT_PATH_RE = /^\/[A-Za-z0-9/_\-.~?=&%]*$/;
const NEXT_PATH_MAX_LENGTH = 256;
const BLOCKED_ROOTS = new Set(['login', 'logout', 'verify', 'rsvp', 'magic-link']);

// Byte-wise, and never throwing: `decodeURIComponent` throws on a lone `%`, which
// the whitelist allows, so the server's lenient `unquote` is mirrored instead.
// Only ASCII matters to the checks below (`.`, `/`, `?` and the door names).
const percentDecode = (value) =>
  value.replace(/%([0-9a-fA-F]{2})/g, (_, hex) => String.fromCharCode(parseInt(hex, 16)));

export function safeNextPath(value) {
  if (typeof value !== 'string' || value.length > NEXT_PATH_MAX_LENGTH) return '';
  if (!NEXT_PATH_RE.test(value) || value.startsWith('//')) return '';
  const decoded = percentDecode(value);
  if (decoded.includes('..')) return '';
  const path = decoded.split('?')[0];
  if (path === '/' || BLOCKED_ROOTS.has(path.split('/')[1].toLowerCase())) return '';
  return value;
}

/**
 * The `/login` URL that remembers `{ pathname, search }` (a router or window
 * location), or plain `/login` when that is not somewhere a login can return to.
 */
export function loginPathFor({ pathname = '', search = '' } = {}) {
  const next = safeNextPath(`${pathname}${search}`);
  return next ? `/login?next=${encodeURIComponent(next)}` : '/login';
}

/**
 * The filename OIUEEI's own export endpoints set via `Content-Disposition`,
 * or `fallback` when it's missing (a network layer that stripped the header,
 * never the server in normal operation). Shared rather than parsed per page
 * so the two export downloads (account, collection) can't drift in how they
 * read it.
 */
export function filenameFromResponse(res, fallback) {
  const header = res.headers.get('Content-Disposition') || '';
  const match = header.match(/filename="?([^"]+)"?/);
  return match ? match[1] : fallback;
}

/**
 * Hand an already-fetched `Blob` to the browser as a file download.
 *
 * There is no declarative way to do this: a plain `<a download>` needs a URL
 * that only exists once the response has arrived, so what is left is a dozen
 * lines of imperative DOM. Copied per page they drift, and the two ways they
 * drift are both invisible in the happy path — an object URL that is never
 * revoked pins the whole blob in memory for the life of the tab, and an anchor
 * left in the document is a stray focusable element between the real controls.
 *
 * **The caller owns the request and its failures.** What a 429 or a 500 should
 * say differs per page — a Notification here, a Toast there — and this function
 * never sees the response, only the bytes and the name they should land under.
 */
export default function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

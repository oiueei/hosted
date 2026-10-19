// A DRF list answers one page (20 by default, `page_size` up to 100) with a `next`
// link; a screen that shows "all of mine" has to follow it to the end or it
// silently drops everything past the first page. `next` is an absolute URL, so the
// origin is stripped to keep the request on the app's own `apiFetch`.
const MAX_PAGES = 50;

/**
 * Reads every page of a paginated list.
 *
 * Resolves `{ rows, complete }`. A first page that cannot be read rejects (or, for
 * an HTTP error, resolves `{ rows: [], complete: false }`), so the caller keeps its
 * own failure path; a *later* page that fails leaves what was read so far with
 * `complete: false`, so a screen can show the groups it has and say the list is
 * partial instead of showing nothing.
 */
export async function fetchAllPages(apiFetch, path, { signal } = {}) {
  const rows = [];
  let next = path;
  for (let page = 0; next; page += 1) {
    if (page === MAX_PAGES) return { rows, complete: false };
    let res;
    try {
      res = await apiFetch(next, { signal });
    } catch (err) {
      if (page === 0 || signal?.aborted) throw err;
      return { rows, complete: false };
    }
    if (!res.ok) return { rows, complete: false };
    const data = await res.json();
    rows.push(...(data.results || []));
    next = data.next ? data.next.replace(/^https?:\/\/[^/]+/, '') : null;
  }
  return { rows, complete: true };
}

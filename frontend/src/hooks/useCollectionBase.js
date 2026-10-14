import { useEffect } from 'react';
import { useLocation, useNavigate } from 'react-router';
import { COLLECTION_PREFIXES, collectionPath, kindSegment } from '../utils/collectionPath';

const prefixOf = (pathname) => {
  const segment = pathname.split('/')[1];
  return COLLECTION_PREFIXES.includes(segment) ? segment : null;
};

/**
 * The route of the collection a sub-page belongs to, `/{prefix}/{code}`, taken
 * from the prefix the page itself was reached under.
 *
 * For a page that only has the collection's code (`/stall/:code/add`, `…/leave`):
 * its own route already names the kind's prefix, so the links it draws stay on it
 * with no lookup. A page that has loaded the collection hands its `kind` too, and
 * that wins — it is the collection's own word, where the route is only where the
 * reader happened to arrive.
 */
export function useCollectionBase(code, kind) {
  const { pathname } = useLocation();
  if (kind) return collectionPath(code, kind);
  return `/${prefixOf(pathname) || 'collections'}/${code}`;
}

/**
 * Moves a collection page that was reached under the wrong prefix to its own,
 * keeping the rest of the path, the query (`?thing=` of the join page), the hash
 * and the navigation state. A link navigated within the app never meets the
 * server's 301, so this is what makes an old `/collections/X` — or `/stall/X` for
 * a library — end up at its kind's address. Does nothing until `kind` is known.
 */
export function useCanonicalCollectionPath(kind) {
  const { pathname, search, hash, state } = useLocation();
  const navigate = useNavigate();
  useEffect(() => {
    if (!kind) return;
    const wanted = kindSegment(kind);
    const current = prefixOf(pathname);
    if (!current || current === wanted || wanted === 'collections') return;
    const rest = pathname.split('/').slice(2).join('/');
    navigate(`/${wanted}/${rest}${search}${hash}`, { replace: true, state });
  }, [kind, pathname, search, hash, state, navigate]);
}

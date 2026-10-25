import { useEffect, useState } from 'react';
import { apiFetch } from '../services/api';

/**
 * The palettes a curator can pick for a collection: the twelve rows of `theeemes`
 * (`GET /api/v1/theeemes/`, the selector). The app's own palette is another table and
 * is never in the list.
 *
 * Best-effort: a list that cannot be read leaves the selector out rather than the
 * form broken, and the collection keeps the palette it has (or draws one).
 */
export default function useTheeemeList() {
  const [theeemes, setTheeemes] = useState([]);
  useEffect(() => {
    let cancelled = false;
    Promise.resolve()
      .then(() => apiFetch('/api/v1/theeemes/'))
      .then((res) => (res.ok ? res.json() : []))
      .then((data) => {
        if (!cancelled) setTheeemes(Array.isArray(data) ? data : data?.results || []);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);
  return theeemes;
}

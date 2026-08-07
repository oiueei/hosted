import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Button, Notification } from 'hds-react';
import { apiFetch } from '../services/api';
import PageLayout from '../components/PageLayout';
import LoadingSpinner from '../components/LoadingSpinner';
import ThingLinkbox from '../components/ThingLinkbox';
import useTheeeme from '../hooks/useTheeeme';

/**
 * Everything shared with me, across every group I belong to.
 *
 * `GET /api/v1/invited-things/` was written, documented and shipped with no
 * caller at all — the same asymmetry `/owner-bookings/` had. A member of five
 * collections could only see what was in them by opening each one in turn,
 * which is also the question the weekly digest answers by email and the app
 * could not answer at all.
 *
 * Deliberately **not** another button in Home's hero (DESIGN §3 — there are four
 * already): it hangs off the "Shared with me" section, next to the collections
 * it summarises.
 */
export default function SharedThingsPage() {
  const { t } = useTranslation();
  const { btnStyle, btnSecondaryStyle } = useTheeeme();
  const [things, setThings] = useState(null);
  const [next, setNext] = useState(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => { document.title = t('titles.sharedThings'); }, [t]);

  useEffect(() => {
    const controller = new AbortController();
    const { signal } = controller;
    (async () => {
      try {
        const res = await apiFetch('/api/v1/invited-things/', { signal });
        if (signal.aborted) return;
        if (res.ok) {
          const data = await res.json();
          if (signal.aborted) return;
          setThings(data.results || []);
          setNext(data.next || null);
        } else {
          setError(t('sharedThings.errorLoading'));
        }
      } catch {
        if (!signal.aborted) setError(t('common.connectionError'));
      }
    })();
    return () => controller.abort();
  }, [t]);

  const loadMore = async () => {
    if (!next || loadingMore) return;
    setLoadingMore(true);
    try {
      // `next` is an absolute DRF URL; strip the origin so it goes through the
      // Vite proxy in dev and stays same-origin (sends auth cookies) everywhere.
      const res = await apiFetch(next.replace(/^https?:\/\/[^/]+/, ''));
      if (res.ok) {
        const data = await res.json();
        setThings((prev) => [...prev, ...(data.results || [])]);
        setNext(data.next || null);
      }
    } catch {
      setError(t('common.connectionError'));
    } finally {
      setLoadingMore(false);
    }
  };

  // Stable so the memoised cards don't re-render when the pager state moves.
  const handleUpdateThing = useCallback((thingCode, updates) => {
    setThings((prev) => prev.map((thg) => (thg.code === thingCode ? { ...thg, ...updates } : thg)));
  }, []);

  if (error) {
    return (
      <PageLayout title={t('common.error')} backTo="/" backLabel={t('common.home')}>
        <Notification label={t('common.error')} type="error">{error}</Notification>
      </PageLayout>
    );
  }

  if (!things) return <LoadingSpinner />;

  const userCode = localStorage.getItem('userCode');

  return (
    <PageLayout
      title={t('sharedThings.pageTitle')}
      description={t('sharedThings.intro')}
      backTo="/"
      backLabel={t('common.home')}
    >
      {things.length === 0 ? (
        <div>
          <p>{t('sharedThings.empty')}</p>
          <div className="spacer-m" />
          <Link to="/">
            <Button style={btnStyle}>{t('sharedThings.emptyCta')}</Button>
          </Link>
        </div>
      ) : (
        <div className="things-grid">
          {things.map((thing) => (
            <ThingLinkbox
              key={thing.code}
              thing={thing}
              userCode={userCode}
              collectionCode={thing.collection_code}
              collectionHeadline={thing.collection_headline}
              collectionOwner={thing.collection_owner}
              onUpdateThing={handleUpdateThing}
            />
          ))}
        </div>
      )}

      {next && (
        <>
          <div className="spacer-m" />
          <Button variant="secondary" onClick={loadMore} disabled={loadingMore} style={btnSecondaryStyle}>
            {t('common.loadMore')}
          </Button>
        </>
      )}
    </PageLayout>
  );
}

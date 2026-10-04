import { useEffect, useState } from 'react';
import { useParams, useLocation, useSearchParams } from 'react-router';
import { useTranslation } from 'react-i18next';
import { Koros } from 'hds-react';
import BackLink from '../components/BackLink';
import JoinToAct from '../components/JoinToAct';
import useTheeeme from '../hooks/useTheeeme';
import AccountMenu from '../components/AccountMenu';
import HeroPhoto from '../components/HeroPhoto';
import { apiFetch } from '../services/api';
import { useLocalized } from '../utils/localized';
import useCollectionLanguage from '../hooks/useCollectionLanguage';

/**
 * Login-to-act landing page for a PUBLIC collection. An anonymous visitor who
 * clicks an action button (reserve / order / respond …) on a public collection
 * lands here: they enter their email, the backend (pop-in) joins them to that
 * collection and emails a magic link, and following it drops them back on the
 * collection — now a member who can act. Standard `form-hero` + `Koros` layout,
 * with the collection's own photo (`HeroPhoto`, the same composition as its page)
 * when it has one.
 */
export default function JoinPage() {
  const { code } = useParams();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  // The thing the visitor was trying to act on, if they came from a card/detail
  // "Reserve" click (S13). Passed through to `/auth/join/` so the magic link
  // lands them back on it, not the collection index. A `/join` URL opened cold
  // simply has no `?thing=` and behaves as before.
  const thingCode = searchParams.get('thing') || undefined;
  const { t } = useTranslation();
  const { tc, koro } = useTheeeme();
  const L = useLocalized();
  // The name is seeded from the navigation state when there is one — that
  // renders it with no flicker — but it can't be the only source. Only
  // `ThingLinkbox` passes it; a refresh, `ThingPage`'s reserve button and
  // a /join URL somebody shared all arrive with nothing, and the
  // page then asked a stranger to hand over their email to join "Collection".
  // This is the first screen of the viral funnel, so it fetches the collection
  // itself. Public and ACTIVE by definition (login-to-act only exists there), so
  // an anonymous GET resolves; a private or missing one simply 403/404s and we
  // keep the generic copy rather than inventing a name.
  const [headline, setHeadline] = useState(location.state?.collectionHeadline || '');
  const [collectionLanguage, setCollectionLanguage] = useState('');
  // What a member can do there — the door's first line names exactly that. The
  // API gives both to an anonymous reader of a PUBLIC collection.
  const [mode, setMode] = useState('');
  const [allowedThingTypes, setAllowedThingTypes] = useState([]);
  // The collection's own photo, so the door looks like the page it leads to.
  const [thumbnailUrl, setThumbnailUrl] = useState('');
  // The raw headline, per-language map and all, for the hook to read.
  const [ownerHeadline, setOwnerHeadline] = useState('');
  useCollectionLanguage(collectionLanguage, [ownerHeadline]);

  useEffect(() => {
    document.title = `${t('joinToAct.heading')} — OIUEEI`;
  }, [t]);

  useEffect(() => {
    if (!code) return undefined;
    const controller = new AbortController();
    apiFetch(`/api/v1/collections/${code}/`, { signal: controller.signal })
      .then((res) => (res.ok ? res.json() : Promise.reject()))
      .then((data) => {
        if (data?.headline) setHeadline(L(data.headline));
        setCollectionLanguage(data?.language || '');
        setMode(data?.mode || '');
        setAllowedThingTypes(data?.allowed_thing_types || []);
        setThumbnailUrl(data?.thumbnail_url || '');
        setOwnerHeadline(data?.headline || '');
      })
      .catch(() => {});
    return () => controller.abort();
    // `L` is rebuilt on every language change; re-running for that would only
    // re-fetch to resolve the same map again, and the copy already re-renders.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [code]);

  return (
    <div
      className="form-page"
      style={tc.color_02 ? { backgroundColor: `var(--color-${tc.color_02})` } : undefined}
    >
      <div
        className={`form-hero${thumbnailUrl ? ' form-hero--photo' : ''}`}
        style={tc.color_03 ? { backgroundColor: `var(--color-${tc.color_03})` } : undefined}
      >
        <div className="form-hero-split">
          <div
            className="form-hero-content"
            style={tc.color_05 ? { '--hero-text-color': `var(--color-${tc.color_05})` } : undefined}
          >
            <span className="hero-corners">
              <AccountMenu />
            </span>
            <BackLink to={`/collections/${code}`} label={headline || t('common.collection')} />
            <h1 className="form-hero-title">{t('joinToAct.heading')}</h1>
          </div>
        </div>
        {thumbnailUrl && (
          <HeroPhoto photoUrl={thumbnailUrl} alt={headline} koroType={koro} color03={tc.color_03} />
        )}
        <Koros
          className="form-hero-koros"
          type={koro}
          style={tc.color_02 ? { fill: `var(--color-${tc.color_02})` } : undefined}
        />
      </div>
      <div className="page-container">
        <JoinToAct
          collectionCode={code}
          collectionHeadline={headline}
          thingCode={thingCode}
          mode={mode}
          allowedThingTypes={allowedThingTypes}
        />
      </div>
    </div>
  );
}

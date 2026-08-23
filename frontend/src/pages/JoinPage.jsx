import { useEffect, useState } from 'react';
import { useParams, useLocation } from 'react-router';
import { useTranslation } from 'react-i18next';
import { Koros } from 'hds-react';
import BackLink from '../components/BackLink';
import JoinToAct from '../components/JoinToAct';
import useTheeeme from '../hooks/useTheeeme';
import ContactCorner from '../components/ContactCorner';
import { apiFetch } from '../services/api';
import { useLocalized } from '../utils/localized';

/**
 * Login-to-act landing page for a PUBLIC collection. An anonymous visitor who
 * clicks an action button (reserve / order / respond …) on a public collection
 * lands here: they enter their email, the backend (pop-in) joins them to that
 * collection and emails a magic link, and following it drops them back on the
 * collection — now a member who can act. Standard `form-hero` + `Koros` layout.
 */
export default function JoinPage() {
  const { code } = useParams();
  const location = useLocation();
  const { t } = useTranslation();
  const { tc, koro } = useTheeeme();
  const L = useLocalized();
  // The name is seeded from the navigation state when there is one — that
  // renders it with no flicker — but it can't be the only source. Only
  // `ThingLinkbox` passes it; the hero's own "Join to take part" link, a
  // refresh, and a /join URL somebody shared all arrive with nothing, and the
  // page then asked a stranger to hand over their email to join "Collection".
  // This is the first screen of the viral funnel, so it fetches the collection
  // itself. Public and ACTIVE by definition (login-to-act only exists there), so
  // an anonymous GET resolves; a private or missing one simply 403/404s and we
  // keep the generic copy rather than inventing a name.
  const [headline, setHeadline] = useState(location.state?.collectionHeadline || '');

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
        className="form-hero"
        style={
          tc.color_03
            ? {
                backgroundColor: `var(--color-${tc.color_03})`,
                '--hero-logo-color': `var(--color-${tc.color_02})`,
              }
            : undefined
        }
      >
        <div
          className="form-hero-content"
          style={tc.color_05 ? { '--hero-text-color': `var(--color-${tc.color_05})` } : undefined}
        >
          <ContactCorner />
          <BackLink to={`/collections/${code}`} label={headline || t('common.collection')} />
          <h1 className="form-hero-title">{t('joinToAct.heading')}</h1>
        </div>
        <Koros
          className="form-hero-koros"
          type={koro}
          style={tc.color_02 ? { fill: `var(--color-${tc.color_02})` } : undefined}
        />
      </div>
      <div className="page-container">
        <JoinToAct collectionCode={code} collectionHeadline={headline} />
      </div>
    </div>
  );
}

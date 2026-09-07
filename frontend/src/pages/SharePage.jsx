import { useEffect, useState } from 'react';
import { useParams } from 'react-router';
import { useTranslation } from 'react-i18next';
import { apiFetch } from '../services/api';
import { useLocalized } from '../utils/localized';
import MagicLinkJoinPage from '../components/MagicLinkJoinPage';

/**
 * `/share/{token}` landing. Renders the shared `MagicLinkJoinPage`, but first
 * asks `GET /share/{token}/preview/` for the collection's name and description
 * so the page can say "Join the Chalmercadillo" instead of "Join us on OIUEEI"
 * — someone handed the link on WhatsApp otherwise has no idea what it opens.
 *
 * The GET is best-effort: on any failure (an unknown or revoked token — the
 * endpoint 404s those on purpose — or a network error) the page falls straight
 * back to the generic copy. A visible error here would be worse than a plain
 * "Join us" line, and the join form still works either way.
 */
export default function SharePage() {
  const { token } = useParams();
  const { t } = useTranslation();
  const L = useLocalized();
  const [preview, setPreview] = useState(null);

  useEffect(() => {
    let cancelled = false;
    apiFetch(`/api/v1/share/${token}/preview/`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (!cancelled && data && data.headline) setPreview(data);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [token]);

  const name = preview ? L(preview.headline) : null;
  const description = preview ? L(preview.description) : null;

  return (
    <MagicLinkJoinPage
      ns="share"
      docTitleKey="titles.share"
      titleKey="share.pageTitle"
      descriptionKey="share.pageDescription"
      docTitleText={name ? t('titles.shareNamed', { name }) : undefined}
      titleText={name ? t('share.pageTitleNamed', { name }) : undefined}
      descriptionText={name ? t('share.pageDescriptionNamed', { name }) : undefined}
      collectionDescription={description || undefined}
      extraBody={{ share_token: token }}
    />
  );
}

import { useEffect, useRef, useState } from 'react';
import { useParams, Link } from 'react-router';
import { useTranslation } from 'react-i18next';
import { Notification, Koros } from 'hds-react';
import useTheeeme from '../hooks/useTheeeme';
import ContactCorner from '../components/ContactCorner';
import { useLocalized } from '../utils/localized';

/**
 * Landing page for the one-click "stop the summaries from this group" link in
 * every digest footer. Public route — the signed token in the URL is the whole
 * credential, and requiring a login here would defeat the point: this is the
 * unsubscribe, and it must work for someone who has forgotten they have an
 * account.
 *
 * **The POST fires from JS on mount, not from the email's GET.** A mail client's
 * link scanner or a prefetch loads the URL without running JavaScript, so it
 * can't unsubscribe anyone on the member's behalf — the same guard the booking
 * accept/reject links use (see `core/views/CLAUDE.md` → VerifyLinkView). The ref
 * stops React 19 StrictMode's double-invoked effect from POSTing twice; the
 * endpoint is idempotent anyway, but a second call would be noise.
 */
export default function DigestMutePage() {
  const { token } = useParams();
  const { t } = useTranslation();
  const { tc, koro } = useTheeeme();
  const L = useLocalized();
  const [status, setStatus] = useState('working'); // 'working' | 'done' | 'error'
  const [headline, setHeadline] = useState('');
  const sentRef = useRef(false);

  useEffect(() => { document.title = t('digestMute.pageTitle'); }, [t]);

  useEffect(() => {
    if (sentRef.current) return;
    sentRef.current = true;
    (async () => {
      try {
        const res = await fetch(`/api/v1/digest/mute/${token}/`, { method: 'POST' });
        if (!res.ok) { setStatus('error'); return; }
        const data = await res.json().catch(() => ({}));
        setHeadline(data.collection_headline || '');
        setStatus('done');
      } catch {
        setStatus('error');
      }
    })();
  }, [token]);

  return (
    <div
      className="form-page"
      style={tc.color_02 ? { backgroundColor: `var(--color-${tc.color_02})` } : undefined}
    >
      <div
        className="form-hero"
        style={tc.color_03 ? { backgroundColor: `var(--color-${tc.color_03})`, '--hero-logo-color': `var(--color-${tc.color_02})` } : undefined}
      >
        <div className="form-hero-content" style={tc.color_05 ? { '--hero-text-color': `var(--color-${tc.color_05})` } : undefined}>
          <ContactCorner />
          <h1 className="form-hero-title">{t('digestMute.title')}</h1>
        </div>
        <Koros
          className="form-hero-koros"
          type={koro}
          style={tc.color_02 ? { fill: `var(--color-${tc.color_02})` } : undefined}
        />
      </div>
      <div className="page-container">
        {status === 'working' && <p className="section-mt">{t('digestMute.working')}</p>}
        {status === 'done' && (
          <>
            <Notification label={t('digestMute.doneLabel')} type="success">
              {headline
                ? t('digestMute.doneNamed', { collection: L(headline) })
                : t('digestMute.done')}
            </Notification>
            <p className="section-mt measure">{t('digestMute.stillGet')}</p>
          </>
        )}
        {status === 'error' && (
          <Notification label={t('common.error')} type="error">
            {t('digestMute.error')}
          </Notification>
        )}
        <p className="section-mt">
          <Link to="/">{t('common.home')}</Link>
        </p>
      </div>
    </div>
  );
}

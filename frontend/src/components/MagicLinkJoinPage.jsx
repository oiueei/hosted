import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';
import { TextInput, Button, Notification } from 'hds-react';
import useTheeeme from '../hooks/useTheeeme';
import useJoin from '../hooks/useJoin';
import PageLayout from './PageLayout';

/**
 * Shared join landing page: an email form that POSTs to `/auth/join/` and
 * swaps into a sent/error Notification. `SharePage` — and any door a deployment
 * adds — is this page with different copy and payload (`extraBody` carries
 * SharePage's `share_token`). JoinPage's variant (`JoinToAct`) stays separate on purpose —
 * it renders unboxed inside another page's hero and reports errors inline —
 * but the request itself is shared: both call `useJoin`.
 *
 * Props:
 * - `ns`: i18n namespace for the form strings ('share' here; a deployment
 *   that adds its own door passes its own, supplying the copy through
 *   `deploymentI18n` rather than editing the locale files)
 *   (emailLabel/emailPlaceholder/magicLinkSent/errorSendingLink/joining/join/
 *   alreadyHaveAccount) and the email input id (`{ns}-email`).
 * - `docTitleKey` / `titleKey` / `descriptionKey`: full i18n keys for the
 *   document title, hero title and intro paragraph (their names differ per page).
 * - `extraBody`: extra fields merged into the POST body.
 * - `endpoint`: which URL the form POSTs to (see `useJoin`) — every upstream
 *   caller leaves this at the default `/auth/join/`; a deployment's own open
 *   door passes its own.
 */
export default function MagicLinkJoinPage({
  ns,
  docTitleKey,
  titleKey,
  descriptionKey,
  extraBody,
  endpoint,
}) {
  const { t } = useTranslation();
  useEffect(() => {
    document.title = t(docTitleKey);
  }, [t, docTitleKey]);
  const { email, setEmail, loading, status, message, submit } = useJoin({
    sentMessageKey: `${ns}.magicLinkSent`,
    errorMessageKey: `${ns}.errorSendingLink`,
    extraBody,
    endpoint,
  });

  const { btnStyle } = useTheeeme();

  return (
    <PageLayout title={t(titleKey)}>
      <p className="section-mt measure">{t(descriptionKey)}</p>
      {status ? (
        <>
          <Notification
            autofocus
            label={status === 'success' ? t('common.sent') : t('common.error')}
            type={status}
            style={{ marginTop: 'var(--spacing-m)' }}
          >
            {message}
          </Notification>
          {status === 'success' && <p className="section-mt">{t('common.closeThisTab')}</p>}
        </>
      ) : (
        <form onSubmit={submit} className="measure">
          <TextInput
            id={`${ns}-email`}
            label={t(`${ns}.emailLabel`)}
            type="email"
            placeholder={t(`${ns}.emailPlaceholder`)}
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            className="section-mt"
          />
          <div>
            <Button type="submit" fullWidth disabled={loading} style={btnStyle}>
              {loading ? t(`${ns}.joining`) : t(`${ns}.join`)}
            </Button>
          </div>
        </form>
      )}
      {/* Every door this component serves (/share/:token, plus any a deployment
          adds) creates a real
          account from the typed email, so the privacy information has to be
          reachable *here* — at the moment data is collected — not only on
          /login. Reuses login.legalLink: same destination, same words. */}
      <p className="measure" style={{ marginTop: 'var(--spacing-s)' }}>
        <Link to="/legal" className="legal-link">
          {t('login.legalLink')}
        </Link>
      </p>
      <p className="measure" style={{ marginTop: 'var(--spacing-m)' }}>
        <Link to="/login">{t(`${ns}.alreadyHaveAccount`)}</Link>
      </p>
    </PageLayout>
  );
}

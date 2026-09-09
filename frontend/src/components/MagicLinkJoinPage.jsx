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
 * - `docTitleText` / `titleText` / `descriptionText`: literal strings that
 *   override the corresponding `*Key` when set. `SharePage` uses them to show
 *   the real collection name once its `/share/{token}/preview/` GET lands, so a
 *   stranger sees "Join the Chalmercadillo", not "Join us on OIUEEI".
 * - `collectionDescription`: the collection's own description (already resolved
 *   to the reader's language) — a quiet paragraph under the intro when present.
 * - `extraBody`: extra fields merged into the POST body.
 * - `endpoint`: which URL the form POSTs to (see `useJoin`) — every upstream
 *   caller leaves this at the default `/auth/join/`; a deployment's own open
 *   door passes its own.
 * - `children`: rendered just under the form, above the `/legal` and `/login`
 *   links. Upstream `SharePage` passes none; a deployment's door uses it for
 *   its own footer link (the hosted `/popin` points it at its `/faq`).
 */
export default function MagicLinkJoinPage({
  ns,
  docTitleKey,
  titleKey,
  descriptionKey,
  docTitleText,
  titleText,
  descriptionText,
  collectionDescription,
  extraBody,
  endpoint,
  children,
}) {
  const { t } = useTranslation();
  const heroTitle = titleText || t(titleKey);
  const intro = descriptionText || t(descriptionKey);
  useEffect(() => {
    document.title = docTitleText || t(docTitleKey);
  }, [t, docTitleKey, docTitleText]);
  const { email, setEmail, loading, status, message, submit } = useJoin({
    sentMessageKey: `${ns}.magicLinkSent`,
    errorMessageKey: `${ns}.errorSendingLink`,
    extraBody,
    endpoint,
  });

  const { btnStyle } = useTheeeme();

  return (
    <PageLayout title={heroTitle}>
      <p className="section-mt measure">{intro}</p>
      {collectionDescription && (
        <p
          className="measure"
          style={{ marginTop: 'var(--spacing-s)', color: 'var(--color-black-60)' }}
        >
          {collectionDescription}
        </p>
      )}
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
      {children && (
        <div className="measure" style={{ marginTop: 'var(--spacing-m)' }}>
          {children}
        </div>
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

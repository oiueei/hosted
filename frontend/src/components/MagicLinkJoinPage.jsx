import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';
import { TextInput, Button, Notification } from 'hds-react';
import useTheeeme from '../hooks/useTheeeme';
import usePopIn from '../hooks/usePopIn';
import PageLayout from './PageLayout';

/**
 * Shared pop-in landing page: an email form that POSTs to `/auth/pop-in/` and
 * swaps into a sent/error Notification. `PopInPage` and `SharePage` are this
 * page with different copy and payload (`extraBody` carries SharePage's
 * `share_token`). JoinPage's variant (`JoinToAct`) stays separate on purpose —
 * it renders unboxed inside another page's hero and reports errors inline —
 * but the request itself is shared: both call `usePopIn`.
 *
 * Props:
 * - `ns`: i18n namespace ('popin' | 'share') for the form strings
 *   (emailLabel/emailPlaceholder/magicLinkSent/errorSendingLink/joining/join/
 *   alreadyHaveAccount) and the email input id (`{ns}-email`).
 * - `docTitleKey` / `titleKey` / `descriptionKey`: full i18n keys for the
 *   document title, hero title and intro paragraph (their names differ per page).
 * - `extraBody`: extra fields merged into the POST body.
 */
export default function MagicLinkJoinPage({ ns, docTitleKey, titleKey, descriptionKey, extraBody }) {
  const { t } = useTranslation();
  useEffect(() => { document.title = t(docTitleKey); }, [t, docTitleKey]);
  const { email, setEmail, loading, status, message, submit } = usePopIn({
    sentMessageKey: `${ns}.magicLinkSent`,
    errorMessageKey: `${ns}.errorSendingLink`,
    extraBody,
  });

  const { btnStyle } = useTheeeme();

  return (
    <PageLayout title={t(titleKey)}>
      <p className="section-mt measure">{t(descriptionKey)}</p>
      {status ? (
        <>
          <Notification
            label={status === 'success' ? t('common.sent') : t('common.error')}
            type={status}
            style={{ marginTop: 'var(--spacing-m)' }}
          >
            {message}
          </Notification>
          {status === 'success' && (
            <p className="section-mt">{t('popin.closeThisTab')}</p>
          )}
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
      {/* Both doors this component serves (/popin, /share/:token) create a real
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

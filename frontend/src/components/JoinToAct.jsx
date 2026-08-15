import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';
import { TextInput, Button, Notification } from 'hds-react';
import useTheeeme from '../hooks/useTheeeme';
import useJoin from '../hooks/useJoin';

/**
 * "Log in to act" body rendered by JoinPage for an anonymous visitor on a PUBLIC
 * collection or thing. Captures an email and POSTs it to `/auth/join/` along
 * with the collection code: the backend adds the visitor to that public
 * collection's invitees and emails a magic link, so once they follow it they're
 * a member and can reserve, ask and contribute. No account or prior invitation
 * is needed — and the code only ever joins a PUBLIC collection (the backend
 * silently ignores it otherwise).
 *
 * The request itself lives in `useJoin`, shared with `MagicLinkJoinPage`
 * (`/popin`, `/share/:token`); only the presentation differs.
 */
export default function JoinToAct({ collectionCode, collectionHeadline }) {
  const { t } = useTranslation();
  const { btnStyle } = useTheeeme();
  const { email, setEmail, loading, status, message, submit } = useJoin({
    sentMessageKey: 'joinToAct.sentBody',
    errorMessageKey: 'joinToAct.error',
    extraBody: { collection_code: collectionCode },
  });

  if (status === 'success') {
    return (
      <>
        <Notification label={t('joinToAct.sent')} type="success">
          {message}
        </Notification>
        <p className="section-mt">{t('popin.closeThisTab')}</p>
      </>
    );
  }

  const body = (
    <>
      <p style={{ marginTop: 0 }}>
        {collectionHeadline
          ? t('joinToAct.bodyNamed', { collection: collectionHeadline })
          : t('joinToAct.body')}
      </p>
      <form onSubmit={submit}>
        <TextInput
          id="join-to-act-email"
          label={t('joinToAct.emailLabel')}
          type="email"
          placeholder={t('joinToAct.emailPlaceholder')}
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
          aria-describedby={status === 'error' ? 'join-to-act-error' : undefined}
        />
        {status === 'error' && (
          <p id="join-to-act-error" role="alert" style={{ color: 'var(--color-error)', marginBottom: 0 }}>
            {message}
          </p>
        )}
        <div style={{ marginTop: 'var(--spacing-s)' }}>
          <Button type="submit" disabled={loading} style={btnStyle}>
            {loading ? t('joinToAct.joining') : t('joinToAct.join')}
          </Button>
        </div>
      </form>
      {/* Third door that mints an account from a typed email (see
          MagicLinkJoinPage) — the privacy information travels with it. */}
      <p style={{ marginBottom: 'var(--spacing-2-xs)' }}>
        <Link to="/legal" className="legal-link">
          {t('login.legalLink')}
        </Link>
      </p>
      <p style={{ marginBottom: 0 }}>
        <Link to="/login">{t('joinToAct.alreadyHaveAccount')}</Link>
      </p>
    </>
  );

  // JoinPage is the only caller: render the body unboxed — the page hero supplies
  // the heading and container.
  return <div style={{ maxWidth: '480px' }}>{body}</div>;
}

import { useTranslation } from 'react-i18next';
import { TextInput, Button, Notification } from 'hds-react';
import ButtonLink from './ButtonLink';
import useTheeeme from '../hooks/useTheeeme';
import useJoin from '../hooks/useJoin';
import { loginPathFor } from '../utils/nextPath';
import { joinActions } from '../utils/joinActions';

/**
 * "Log in to act" body rendered by JoinPage for an anonymous visitor on a PUBLIC
 * collection or thing. Captures an email and POSTs it to `/auth/join/` along
 * with the collection code: the backend adds the visitor to that public
 * collection's invitees and emails a magic link, so once they follow it they're
 * a member and can reserve, ask and contribute. No account or prior invitation
 * is needed — and the code only ever joins a PUBLIC collection (the backend
 * silently ignores it otherwise).
 *
 * The first line promises what a member of THIS collection can do — its own
 * verbs, from the thing types it allows and its mode (`utils/joinActions.js`) —
 * and falls back to the generic sentence until the collection has loaded.
 *
 * The request itself lives in `useJoin`, shared with `MagicLinkJoinPage`
 * (`/share/:token`, and whatever door a deployment adds); only the presentation differs.
 */
export default function JoinToAct({
  collectionCode,
  collectionHeadline,
  thingCode,
  mode,
  allowedThingTypes,
}) {
  const { t, i18n } = useTranslation();
  const { btnStyle, btnSecondaryStyle } = useTheeeme();
  const { email, setEmail, loading, status, message, submit } = useJoin({
    sentMessageKey: 'joinToAct.sentBody',
    errorMessageKey: 'joinToAct.error',
    extraBody: thingCode
      ? { collection_code: collectionCode, thing_code: thingCode }
      : { collection_code: collectionCode },
  });

  // Someone with an account who pressed "Request" on a public group they are not
  // in lands here and picks "already have an account": after the login they go
  // back to the thing they were looking at, or the group, not to Home.
  const returnPath = thingCode
    ? `/collections/${collectionCode}/things/${thingCode}`
    : `/collections/${collectionCode}`;

  // No mode means the collection has not loaded (or a caller that never asks for
  // it): the generic sentence, not a guess at what is allowed.
  const actions =
    collectionHeadline && mode
      ? joinActions({ allowedThingTypes, mode, t, locale: i18n.language })
      : '';

  if (status === 'success') {
    return (
      <>
        <Notification autofocus label={t('joinToAct.sent')} type="success">
          {message}
        </Notification>
        {/* Air between the notice and this line: section-mt
            pinned it flush against the Notification above — same fix as
            MagicLinkJoinPage's, so the two doors end the same way. */}
        <p style={{ marginTop: 'var(--spacing-s)', marginBottom: 'var(--spacing-m)' }}>
          {t('common.closeThisTab')}
        </p>
      </>
    );
  }

  const body = (
    <>
      {/* The door's first line of words, at the front door's pitch size and
          weight (.login-pitch, Body XL bold). A <p>, not an <h2>: JoinPage's
          hero <h1> is real words ("Join"), so this is body copy and must not
          enter the heading outline. No `measure` here — this wrapper already
          sets the column, and the form below shares its width. */}
      <p className="login-pitch">
        {actions
          ? t('joinToAct.bodyActions', { actions, collection: collectionHeadline })
          : t('joinToAct.body')}
      </p>
      <form onSubmit={submit} style={{ marginTop: 'var(--spacing-m)' }}>
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
          <p
            id="join-to-act-error"
            role="alert"
            style={{ color: 'var(--color-error)', marginBottom: 0 }}
          >
            {message}
          </p>
        )}
        <div style={{ marginTop: 'var(--spacing-s)' }}>
          <Button type="submit" fullWidth disabled={loading} style={btnStyle}>
            {loading ? t('joinToAct.joining') : t('joinToAct.join')}
          </Button>
        </div>
      </form>
      {/* A secondary button under the primary one, as wide as it is (the wrapper sets
          the column, so no `.measure` here): someone who already has an account is one
          button away from signing in, and the sign-in brings them back to what they came
          for. */}
      <div style={{ marginTop: 'var(--spacing-l)' }}>
        <ButtonLink to={loginPathFor({ pathname: returnPath })} fullWidth style={btnSecondaryStyle}>
          {t('joinToAct.alreadyHaveAccount')}
        </ButtonLink>
      </div>
    </>
  );

  // JoinPage is the only caller: render the body unboxed — the page hero supplies
  // the heading and container.
  return <div style={{ maxWidth: '480px' }}>{body}</div>;
}

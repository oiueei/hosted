import { useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router';
import { useTranslation } from 'react-i18next';
import { Button, Notification } from 'hds-react';
import { apiFetch, extractApiError } from '../services/api';
import { useLocalized } from '../utils/localized';
import MagicLinkJoinPage from '../components/MagicLinkJoinPage';
import StatusRegion from '../components/StatusRegion';
import useCollectionLanguage from '../hooks/useCollectionLanguage';
import useTheeeme from '../hooks/useTheeeme';

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
 *
 * **A reader who already has a session gets one button, not the form**
 * (`POST /share/{token}/join/`): asking for an email and mailing a magic link to
 * someone who is signed in is email, inbox, link, back, and in a neighbourhood
 * the same people are in several groups while this link is the main viral route.
 * "Use another email instead" brings the form back for a shared computer. An
 * expired session needs nothing here: `apiFetch` sends them to
 * `/login?next=/share/{token}` and the magic link brings them back to the button.
 */
export default function SharePage() {
  const { token } = useParams();
  const { t } = useTranslation();
  const L = useLocalized();
  const navigate = useNavigate();
  const { btnStyle } = useTheeeme();
  const [preview, setPreview] = useState(null);
  const [useAnotherEmail, setUseAnotherEmail] = useState(false);
  const [joining, setJoining] = useState(false);
  const [joinError, setJoinError] = useState('');
  // A ref, not the `joining` state, keeps a second press from asking again: two
  // activations in the same tick both run with the state of the render before
  // either has set it (the reason `useJoin` guards its submit the same way).
  const joiningRef = useRef(false);

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
  useCollectionLanguage(preview?.language, [preview?.headline, preview?.description]);

  const acceptWithSession = async () => {
    if (joiningRef.current) return;
    joiningRef.current = true;
    setJoining(true);
    setJoinError('');
    try {
      const res = await apiFetch(`/api/v1/share/${token}/join/`, { method: 'POST' });
      if (res.ok) {
        const { collection } = await res.json();
        navigate(`/collections/${collection}`);
        return;
      }
      if (res.status === 404) {
        setJoinError(t('share.linkGone'));
      } else if (res.status === 429) {
        // The hourly limit has no body; the operator's daily ceiling says why.
        setJoinError((await extractApiError(res)) || t('common.tooManyAttempts'));
      } else {
        setJoinError((await extractApiError(res)) || t('joinToAct.error'));
      }
    } catch (err) {
      // A session that ran out is `apiFetch` already redirecting to the login;
      // saying "connection error" over that would be a lie for a moment.
      if (err?.message !== 'Unauthorised') setJoinError(t('common.connectionError'));
    } finally {
      joiningRef.current = false;
      setJoining(false);
    }
  };

  const signedInAction =
    localStorage.getItem('userCode') && !useAnotherEmail ? (
      <div className="measure">
        <Button fullWidth disabled={joining} style={btnStyle} onClick={acceptWithSession}>
          {name ? t('share.joinSignedIn', { name }) : t('share.joinSignedInGeneric')}
        </Button>
        <StatusRegion>
          {joinError && (
            <Notification
              type="error"
              label={t('common.error')}
              style={{ marginTop: 'var(--spacing-s)' }}
            >
              {joinError}
            </Notification>
          )}
        </StatusRegion>
        {/* Quiet, like the other one-line alternatives on the door pages: for a
            shared computer, where the session is not this person's. */}
        <p style={{ marginTop: 'var(--spacing-s)' }}>
          <button
            type="button"
            className="digest-pref-button"
            onClick={() => setUseAnotherEmail(true)}
          >
            {t('share.useAnotherEmail')}
          </button>
        </p>
      </div>
    ) : undefined;

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
      signedInAction={signedInAction}
    />
  );
}

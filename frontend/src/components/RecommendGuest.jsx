import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button, Notification, TextInput, TextArea } from 'hds-react';
import { apiFetch, extractApiError } from '../services/api';
import useTheeeme from '../hooks/useTheeeme';

/**
 * A member recommending someone to the collection's owner.
 *
 * Members could not bring anyone in at all: every new person cost an owner
 * action, so a group grew only as fast as one person worked at it. This is the
 * other half — but the owner is not a bottleneck to route around. The group may
 * be closed, may run on subscriptions, papers or rules of admission, so the
 * owner still decides and **nothing reaches the recommended person until they
 * do**. The copy says so plainly: a member who thinks they just sent an
 * invitation would be misled.
 *
 * "Recommend", not "invite" or "propose": the verb carries that you are putting
 * your name behind this person — which the invitation itself will say, if the
 * owner agrees.
 *
 * Collapsed behind its own button so a group that never uses it costs one quiet
 * line in the hero (DESIGN §3).
 */
export default function RecommendGuest({ collectionCode, ownerName }) {
  const { t } = useTranslation();
  const { btnStyle, btnSecondaryStyle } = useTheeeme();
  const [open, setOpen] = useState(false);
  const [email, setEmail] = useState('');
  const [note, setNote] = useState('');
  const [sending, setSending] = useState(false);
  const [result, setResult] = useState(null);

  const submit = async (e) => {
    e.preventDefault();
    setSending(true);
    setResult(null);
    try {
      const res = await apiFetch(`/api/v1/collections/${collectionCode}/invite/propose/`, {
        method: 'POST',
        body: JSON.stringify({ email, note }),
      });
      if (res.ok) {
        setResult({ type: 'success', message: t('recommend.sent', { owner: ownerName }) });
        setEmail('');
        setNote('');
      } else if (res.status === 429) {
        setResult({ type: 'error', message: t('common.tooManyAttempts') });
      } else {
        setResult({ type: 'error', message: (await extractApiError(res)) || t('recommend.error') });
      }
    } catch {
      setResult({ type: 'error', message: t('common.connectionError') });
    }
    setSending(false);
  };

  if (!open) {
    return (
      <p className="recommend-open">
        <button type="button" className="digest-pref-button" onClick={() => setOpen(true)}>
          {t('recommend.openLink')}
        </button>
      </p>
    );
  }

  return (
    <div className="recommend-box">
      <p className="recommend-intro">{t('recommend.intro', { owner: ownerName })}</p>
      {result && (
        <Notification
          label={result.type === 'success' ? t('common.sent') : t('common.error')}
          type={result.type}
          style={{ marginBottom: 'var(--spacing-s)' }}
        >
          {result.message}
        </Notification>
      )}
      <form onSubmit={submit} className="form-grid">
        <TextInput
          id="recommend-email"
          label={t('recommend.emailLabel')}
          type="email"
          placeholder={t('recommend.emailPlaceholder')}
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />
        <TextArea
          id="recommend-note"
          label={t('recommend.noteLabel')}
          helperText={t('recommend.noteHelper', { owner: ownerName })}
          value={note}
          onChange={(e) => setNote(e.target.value)}
          maxLength={256}
        />
        <div className="button-row-wide">
          <Button type="submit" disabled={sending || !email.trim()} style={btnStyle}>
            {sending ? t('common.sending') : t('recommend.send')}
          </Button>
          <Button
            variant="secondary"
            style={btnSecondaryStyle}
            onClick={() => { setOpen(false); setResult(null); }}
          >
            {t('common.close')}
          </Button>
        </div>
      </form>
    </div>
  );
}

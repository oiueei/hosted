import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button, Notification, TextInput, TextArea } from 'hds-react';
import { apiFetch, extractApiError } from '../services/api';
import useTheeeme from '../hooks/useTheeeme';
import StatusRegion from './StatusRegion';

/**
 * The form a member fills in to recommend someone to the collection.
 *
 * Members could not bring anyone in at all: every new person cost a curator
 * action, so a group grew only as fast as one person worked at it. This is the
 * other half — but whoever runs the group is not a bottleneck to route around.
 * The group may be closed, may run on subscriptions, papers or rules of
 * admission, so the curators still decide and **nothing reaches the recommended
 * person until they do**. The copy says so plainly: a member who thinks they
 * just sent an invitation would be misled.
 *
 * The button that opens this says "Invite someone" (CA, 2026-10-03) — it is the
 * word a member looks for — while everything in here says "Recommend" and that
 * the decision is not theirs, which is what keeps that promise honest: the verb
 * carries that you are putting your name behind this person, which the
 * invitation itself will say, if a curator agrees. "Recommend", not "propose".
 *
 * It paints the form and nothing else. The toggle lives with `CollectionPage`'s
 * member row, because it has to sit beside "Add thing" in a row this component
 * cannot see: the page owns whether the form is open (and mounts it only then,
 * so closing it also drops a half-typed draft and a stale confirmation) and
 * passes `onClose` for the form's own "Close", which hands the focus back to
 * that button. `id` is what the button's `aria-controls` names.
 */
export default function RecommendGuest({ id, collectionCode, ownerName, onClose }) {
  const { t } = useTranslation();
  const { btnStyle, btnSecondaryStyle } = useTheeeme();
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

  return (
    <div id={id} className="recommend-box">
      <p className="recommend-intro">{t('recommend.intro', { owner: ownerName })}</p>
      <StatusRegion>
        {result && (
          <Notification
            label={result.type === 'success' ? t('common.sent') : t('common.error')}
            type={result.type}
            style={{ marginBottom: 'var(--spacing-s)' }}
          >
            {result.message}
          </Notification>
        )}
      </StatusRegion>
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
          label={t('recommend.noteLabel', { owner: ownerName })}
          helperText={t('recommend.noteHelper', { owner: ownerName })}
          value={note}
          onChange={(e) => setNote(e.target.value)}
          maxLength={256}
        />
        <div className="button-row-wide">
          <Button type="submit" disabled={sending || !email.trim()} style={btnStyle}>
            {sending ? t('common.sending') : t('recommend.send')}
          </Button>
          <Button variant="secondary" style={btnSecondaryStyle} onClick={onClose}>
            {t('common.close')}
          </Button>
        </div>
      </form>
    </div>
  );
}

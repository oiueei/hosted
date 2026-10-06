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
 * The button that opens this says "Invite someone" — it is the
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
 *
 * **Who decides, in four sentences.** With no co-curators the founder is the
 * only one who decides and the copy names them (`{owner}`). With any, it is the
 * team — any of them can approve the recommendation and all of them read the
 * note — so the four sentences that named the founder have `_team` twins that
 * name the curators instead (the same case as the "we have told
 * the curators" wording of the request emails). They promise only what is true
 * today: the server still notifies the founder alone (`create_proposal`, a
 * decision still pending), so none of them says the curators were
 * told or that anything was sent to them. `coOwnerCount` is how many
 * co-curators the page knows of (`collection.co_owners`, which members get).
 */
export default function RecommendGuest({
  id,
  collectionCode,
  ownerName,
  coOwnerCount = 0,
  onClose,
}) {
  const { t } = useTranslation();
  const team = coOwnerCount > 0;
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
        setResult({
          type: 'success',
          message: team ? t('recommend.sent_team') : t('recommend.sent', { owner: ownerName }),
        });
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
      <p className="recommend-intro">
        {team ? t('recommend.intro_team') : t('recommend.intro', { owner: ownerName })}
      </p>
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
          label={
            team ? t('recommend.noteLabel_team') : t('recommend.noteLabel', { owner: ownerName })
          }
          helperText={
            team ? t('recommend.noteHelper_team') : t('recommend.noteHelper', { owner: ownerName })
          }
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

import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button, Notification } from 'hds-react';
import { apiFetch, extractApiError } from '../services/api';
import { localizedCounter } from '../utils/localized';
import StatusRegion from './StatusRegion';

/**
 * "Send me a test email" under a collection's email note.
 *
 * The note only ever appears in the emails a *requester* receives, and a
 * curator can't request their own things — so it was written blind. A preview
 * on this page would lie: the email renders a narrower Markdown than
 * `MarkdownText` (no headings, no tables, a link's host printed after it). So
 * the server mails the curator the draft as typed, through the email's own
 * renderer and layout, every language version under its own name
 * (`POST /collections/{code}/email-note/test/`). Nothing is saved by it.
 *
 * Edit only: a collection being created has no code to test against yet.
 */
export default function EmailNoteTest({ collectionCode, note, buttonStyle }) {
  const { t } = useTranslation();
  const [sending, setSending] = useState(false);
  const [result, setResult] = useState(null);
  const empty = !note.trim();
  const over = localizedCounter(note, 512).over;

  const send = async () => {
    setSending(true);
    setResult(null);
    try {
      const res = await apiFetch(`/api/v1/collections/${collectionCode}/email-note/test/`, {
        method: 'POST',
        body: JSON.stringify({ email_note: note.trim() }),
      });
      if (res.ok) {
        setResult({ type: 'success', message: t('emailNote.testSent') });
      } else if (res.status === 429) {
        setResult({ type: 'error', message: t('common.tooManyAttempts') });
      } else {
        setResult({
          type: 'error',
          message: (await extractApiError(res)) || t('emailNote.testError'),
        });
      }
    } catch {
      setResult({ type: 'error', message: t('common.connectionError') });
    }
    setSending(false);
  };

  return (
    <div>
      <Button
        variant="secondary"
        size="small"
        style={buttonStyle}
        disabled={sending || empty || over}
        onClick={send}
      >
        {sending ? t('common.sending') : t('emailNote.testButton')}
      </Button>
      <StatusRegion>
        {result && (
          <Notification
            type={result.type}
            size="small"
            label={result.type === 'success' ? t('common.sent') : t('common.error')}
            notificationAriaLabel={t('emailNote.testButton')}
            style={{ marginTop: 'var(--spacing-2-xs)' }}
          >
            {result.message}
          </Notification>
        )}
      </StatusRegion>
    </div>
  );
}

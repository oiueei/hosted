import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button, Notification, TextArea } from 'hds-react';
import { apiFetch, apiErrorMessage } from '../../services/api';
import StatusRegion from '../StatusRegion';
import useTheeeme from '../../hooks/useTheeeme';

/**
 * A curator's message to the whole group: a button that opens the form, and the
 * outcome in a live region. It owns its own state; the page only decides whether a
 * curator with guests should see it.
 */
export default function BroadcastBox({ code }) {
  const { t } = useTranslation();
  const { btnStyle, btnSecondaryStyle } = useTheeeme();
  const [broadcastOpen, setBroadcastOpen] = useState(false);
  const [broadcastMessage, setBroadcastMessage] = useState('');
  const [broadcastSending, setBroadcastSending] = useState(false);
  const [broadcastResult, setBroadcastResult] = useState(null);

  const handleBroadcast = async () => {
    setBroadcastSending(true);
    setBroadcastResult(null);
    try {
      const res = await apiFetch(`/api/v1/collections/${code}/broadcast/`, {
        method: 'POST',
        body: JSON.stringify({ message: broadcastMessage }),
      });
      const data = await res.json();
      if (res.ok) {
        setBroadcastResult({
          type: 'success',
          message: t('broadcast.sent', { count: data.recipients }),
        });
        setBroadcastMessage('');
      } else {
        // `detail` first, then `error`, the same order `extractApiError` reads
        // them in: this view answers `{error}` on its own refusals, but the one
        // an owner actually meets is the daily cap (5/day), and that arrives
        // from the rate-limit handler as `{detail}`. Reading only `error` turned
        // "slow down and try again later" into a bare "Error" — no reason, no
        // hint that tomorrow works, on the one screen where the owner is left
        // wondering whether the group got the message.
        setBroadcastResult({
          type: 'error',
          message: apiErrorMessage(data) || t('common.error'),
        });
      }
    } catch {
      setBroadcastResult({ type: 'error', message: t('common.connectionError') });
    }
    setBroadcastSending(false);
  };

  return (
    <>
      <div className="spacer-l" />
      <h2>{t('broadcast.heading')}</h2>
      <div className="spacer-m" />
      {!broadcastOpen ? (
        <div className="button-row-wide">
          <Button
            variant="secondary"
            style={btnSecondaryStyle}
            onClick={() => setBroadcastOpen(true)}
          >
            {t('broadcast.openButton')}
          </Button>
        </div>
      ) : (
        <div className="form-grid">
          {/* The one place in the product where a member learns an address
                  the API takes care never to serve them: the broadcast carries
                  the owner's own email as Reply-To, so replying to the group
                  message is one tap. Worth keeping — without it a broadcast is
                  a megaphone with no way back, and the replies would land on a
                  noreply — but not worth doing without saying so first
                  (DESIGN §6). Their own address, their own send: disclosure is
                  what consent needs here, not a switch. */}
          <TextArea
            id="broadcast-message"
            label={t('broadcast.messageLabel')}
            helperText={t('broadcast.replyToNotice')}
            value={broadcastMessage}
            onChange={(e) => setBroadcastMessage(e.target.value)}
            maxLength={256}
            required
          />
          <StatusRegion>
            {broadcastResult && (
              <Notification
                label={broadcastResult.type === 'success' ? t('common.sent') : t('common.error')}
                type={broadcastResult.type}
                style={{ marginBottom: 'var(--spacing-s)' }}
                dismissible
                closeButtonLabelText={t('common.close')}
                onClose={() => setBroadcastResult(null)}
              >
                {broadcastResult.message}
              </Notification>
            )}
          </StatusRegion>
          <div className="button-row-wide">
            <Button
              style={btnStyle}
              onClick={handleBroadcast}
              disabled={broadcastSending || !broadcastMessage.trim()}
            >
              {broadcastSending ? t('broadcast.sending') : t('broadcast.sendButton')}
            </Button>
            <Button
              variant="secondary"
              style={btnSecondaryStyle}
              onClick={() => {
                setBroadcastOpen(false);
                setBroadcastResult(null);
              }}
            >
              {t('common.close')}
            </Button>
          </div>
        </div>
      )}
    </>
  );
}

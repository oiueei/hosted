import { useTranslation } from 'react-i18next';
import { Button } from 'hds-react';
import useTheeeme from '../../hooks/useTheeeme';

/**
 * The fallback of the automatic join: shown only when joining the group on the
 * reader's behalf itself failed, with the reason and a button to try again.
 */
export default function JoinGroupNudge({ message, joining, joinError, onJoin }) {
  const { t } = useTranslation();
  const { btnStyle } = useTheeeme();

  return (
    <div className="invite-nudge" role="alert">
      <p style={{ margin: 0 }}>{message}</p>
      <div className="button-row-wide" style={{ marginTop: 'var(--spacing-xs)' }}>
        <Button style={btnStyle} disabled={joining} onClick={onJoin}>
          {joining ? t('joinToAct.joining') : t('collectionPage.visitorJoin')}
        </Button>
      </div>
      {joinError && (
        <p role="alert" style={{ color: 'var(--color-error)', marginBottom: 0 }}>
          {t('collectionPage.visitorJoinError')}
        </p>
      )}
    </div>
  );
}

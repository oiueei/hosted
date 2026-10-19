import { useState } from 'react';
import { Button, Notification } from 'hds-react';
import { useTranslation } from 'react-i18next';
import useNewVersion from '../hooks/useNewVersion';
import useTheeeme from '../hooks/useTheeeme';

/**
 * "There's a new version" in the corner, once the tab is running an old build
 * (`useNewVersion`). It stays until it is closed or the page is reloaded, and it
 * reloads nothing by itself: whoever is typing must be the one to say when.
 * Bottom right, so it never covers a toast, which sits at the top.
 */
export default function NewVersionNotice() {
  const { t } = useTranslation();
  const { btnStyle } = useTheeeme();
  const available = useNewVersion();
  const [closed, setClosed] = useState(false);

  if (!available || closed) return null;

  return (
    <Notification
      position="bottom-right"
      size="small"
      autoClose={false}
      label={t('common.notice')}
      type="info"
      dismissible
      closeButtonLabelText={t('common.close')}
      onClose={() => setClosed(true)}
    >
      <p>{t('newVersion.body')}</p>
      <Button size="small" style={btnStyle} onClick={() => window.location.reload()}>
        {t('newVersion.reload')}
      </Button>
    </Notification>
  );
}

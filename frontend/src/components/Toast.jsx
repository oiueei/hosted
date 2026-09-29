import { Notification } from 'hds-react';
import { useTranslation } from 'react-i18next';

/**
 * `toast` is `{ type, message }`, or `{ type, messageKey }` when the message is an
 * i18n key to translate where it is painted. A load effect uses the second shape:
 * it must not read `t`, or it runs again whenever `t` changes identity (see
 * `useCollectionLanguage`), and a message it had translated on the way in would
 * stay in the language that happened to be current when the load failed.
 */
export default function Toast({ toast, onClose }) {
  const { t } = useTranslation();

  if (!toast) return null;

  return (
    <Notification
      position="top-right"
      autoClose
      autoCloseDuration={6000}
      aria-live="polite"
      label={toast.type === 'success' ? t('common.done') : t('common.error')}
      type={toast.type}
      dismissible
      closeButtonLabelText={t('common.close')}
      onClose={onClose}
    >
      {toast.messageKey ? t(toast.messageKey) : toast.message}
    </Notification>
  );
}

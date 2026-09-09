import { useTranslation } from 'react-i18next';
import { Notification } from 'hds-react';

// The "you're looking at demo data" banner for a seed / onboarding collection.
//
// It shows on every page of a collection whose `is_onboarding` is true — the
// caller gates on that (`collection.is_onboarding`, or `thing.collection_is_onboarding`).
// The COPY is this deployment's, not the product's: a self-hosted OIUEEI has no
// demo audience (people arrive invited), so upstream ships no `demoNotice.*`
// strings and this renders **nothing**. A deployment that runs an open door
// supplies them through `deploymentI18n` (see `frontend/src/deployment/`) and the
// banner appears — same null-upstream shape as `popInPath` / `FeedbackLink`.
//
// DESIGN_HOSTED.md §1: it must say what IS demo *and* what is not, so a visitor
// doesn't mistake their own new collection for something that gets wiped. Hence
// the two lines — `body` (this is shared and resets) and `realNote` (your own
// collections are real and stay).
export default function DemoNotice() {
  const { t, i18n } = useTranslation();
  if (!i18n.exists('demoNotice.body')) return null;
  return (
    <Notification
      label={t('demoNotice.title')}
      type="alert"
      style={{ marginBottom: 'var(--spacing-m)' }}
    >
      <p style={{ margin: 0 }}>{t('demoNotice.body')}</p>
      <p style={{ margin: 'var(--spacing-2-xs) 0 0' }}>{t('demoNotice.realNote')}</p>
    </Notification>
  );
}

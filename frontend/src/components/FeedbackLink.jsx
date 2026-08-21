import { useTranslation } from 'react-i18next';

// Alpha feedback channel — a quiet line so every page it sits on doubles as a
// listening post, without shouting. This is service-layer policy, not
// product: without VITE_FEEDBACK_URL the door simply isn't offered, the same
// pattern as `popInPath`/`aboutPath` in `src/deployment/` — upstream doesn't
// point anyone's feedback at CA's own form on their behalf. A deployment that
// wants the feature sets the build-time env var and points it at its own.
const FEEDBACK_URL = import.meta.env.VITE_FEEDBACK_URL;

export default function FeedbackLink() {
  const { t } = useTranslation();
  if (!FEEDBACK_URL) return null;
  return (
    <p className="feedback-link">
      {t('feedback.prompt')}{' '}
      <a href={FEEDBACK_URL} target="_blank" rel="noopener noreferrer">
        {t('feedback.cta')} →
      </a>
    </p>
  );
}

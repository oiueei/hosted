import { Link as HdsLink } from 'hds-react';
import { useTranslation } from 'react-i18next';

// Alpha feedback channel. This is service-layer policy, not product: without
// VITE_FEEDBACK_URL the door simply isn't offered, the same pattern as
// `popInPath`/`aboutPath` in `src/deployment/` — upstream doesn't point anyone's
// feedback at CA's own form on their behalf. A deployment that wants the feature
// sets the build-time env var and points it at its own.
const FEEDBACK_URL = import.meta.env.VITE_FEEDBACK_URL;

/**
 * "Ideas and bugs", as a button (CA, 2026-10-03). It was a quiet line — "Something
 * odd? An idea? Tell me →" — that sat under the page's content; CA wants a short
 * button in its place, on Home and at the end of the hosted `/welcome`.
 *
 * It renders **only the `<a>`**, no paragraph around it, so it can sit inside a
 * row of buttons (the hosted `/welcome` puts it in one). Built on HDS `Link` with
 * `useButtonStyles`, the same base as `ButtonLink` (read its docstring): the real
 * button CSS on one `<a>`, one tab stop. `style` carries the theeeme tokens, and
 * the caller decides whether this is the primary or the secondary button — Home
 * passes the secondary, alone.
 *
 * It opens in a new tab, and says so — but not through HDS's `openInNewTab`:
 * that prop appends its label **to the visible text** ("Ideas and bugs (Opens in
 * a new tab.)", in Finnish unless `openInNewTabLabel` is given), which is not the
 * short label CA asked for. So `target` and `rel` are set here and the
 * announcement is the `aria-label` — the visible words first, then the sentence
 * (`common.opensInNewTab`, in the reader's language), the way HDS itself builds
 * the label of an `external` link. The visible name stays inside the accessible
 * one (WCAG 2.5.3).
 *
 * Renders nothing without a URL.
 */
export default function FeedbackLink({ style }) {
  const { t } = useTranslation();
  if (!FEEDBACK_URL) return null;
  const label = t('feedback.button');
  return (
    <HdsLink
      href={FEEDBACK_URL}
      useButtonStyles
      style={style}
      target="_blank"
      rel="noopener noreferrer"
      aria-label={`${label}. ${t('common.opensInNewTab')}`}
    >
      {label}
    </HdsLink>
  );
}

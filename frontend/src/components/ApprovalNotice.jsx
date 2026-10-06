import { Link as HdsLink } from 'hds-react';
import { useTranslation } from 'react-i18next';
import useCapabilities from '../hooks/useCapabilities';
import useTheeeme from '../hooks/useTheeeme';
import { externalFormUrl } from '../utils/externalForms';

/**
 * "Some of these need approval here" — the one line a narrowed deployment owes
 * the person looking at a shorter list than the product has.
 *
 * **Upstream it never renders.** OIUEEI's own policy withholds nothing, so
 * there is nothing to explain and this returns null on every page it sits on.
 * It lives here rather than in a deployment's own directory precisely so the
 * React is identical in both: a deployment narrows the policy on the server and
 * the explanation appears, with nobody editing a form component.
 *
 * Without it, the form silently offers less than the product does and the user
 * is left to conclude the feature does not exist — which for a deployment with
 * a request URL is not even true.
 *
 * **Where to ask is a primary button, "Request access"**, not a
 * link ending in an arrow: the sentence stays as it was, and under it a
 * `.button-row-wide` (the width of the screen on a phone) holds the button. It is
 * made as `FeedbackLink` is — HDS `Link` with `useButtonStyles`, the theeeme's
 * primary tokens, `target="_blank"` and the announcement of the new tab in the
 * `aria-label`, since HDS's own `openInNewTab` prints its label. Without a request
 * URL there is the sentence and no button, as before. These forms already have a
 * primary of their own ("Create" / "Save"); this one is wanted all the same.
 *
 * @param {'collection_modes'|'thing_types'} kind Which capability list to check.
 * @param {Array<{value: string, label: string}>} catalogue Every option the
 *   product has, already labelled — the same list the form would offer if
 *   nothing were withheld.
 */
export default function ApprovalNotice({ kind, catalogue }) {
  const { t, i18n } = useTranslation();
  const capabilities = useCapabilities();
  const { btnStyle } = useTheeeme();

  // Not known yet, or the request failed: say nothing. A wrong "this needs
  // approval" on a deployment that approves everything is worse than silence.
  const allowed = capabilities?.[kind];
  if (!allowed) return null;

  const withheld = catalogue.filter((option) => !allowed.includes(option.value));
  if (withheld.length === 0) return null;

  const list = withheld.map((option) => option.label).join(', ');
  // Where to ask: the deployment's own form for it, in the reader's language
  // (`externalForms.requestAccess`, as written), or the address
  // the server gives (`capabilities.request_url`), as before. It opens in a new tab
  // either way.
  const requestUrl =
    externalFormUrl('requestAccess', i18n.resolvedLanguage || i18n.language) ||
    capabilities.request_url;

  const requestLabel = t('capabilities.requestAccess');

  return (
    <div>
      {/* Two different facts, and the difference is the whole point: somewhere
          to ask means "not yet", nowhere to ask means "not here". Telling
          someone to request access when there is no such page would be worse
          than the disabled control it was meant to explain. */}
      <p className="approval-notice">
        {requestUrl
          ? t('capabilities.needsApproval', { list })
          : t('capabilities.unavailable', { list })}
      </p>
      {requestUrl && (
        <div className="button-row-wide">
          <HdsLink
            href={requestUrl}
            useButtonStyles
            style={btnStyle}
            target="_blank"
            rel="noopener noreferrer"
            aria-label={`${requestLabel}. ${t('common.opensInNewTab')}`}
          >
            {requestLabel}
          </HdsLink>
        </div>
      )}
    </div>
  );
}

import { useTranslation } from 'react-i18next';
import useCapabilities from '../hooks/useCapabilities';

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
 * @param {'collection_modes'|'thing_types'} kind Which capability list to check.
 * @param {Array<{value: string, label: string}>} catalogue Every option the
 *   product has, already labelled — the same list the form would offer if
 *   nothing were withheld.
 */
export default function ApprovalNotice({ kind, catalogue }) {
  const { t } = useTranslation();
  const capabilities = useCapabilities();

  // Not known yet, or the request failed: say nothing. A wrong "this needs
  // approval" on a deployment that approves everything is worse than silence.
  const allowed = capabilities?.[kind];
  if (!allowed) return null;

  const withheld = catalogue.filter((option) => !allowed.includes(option.value));
  if (withheld.length === 0) return null;

  const list = withheld.map((option) => option.label).join(', ');
  const requestUrl = capabilities.request_url;

  return (
    <p className="approval-notice">
      {/* Two different facts, and the difference is the whole point: somewhere
          to ask means "not yet", nowhere to ask means "not here". Telling
          someone to request access when there is no such page would be worse
          than the disabled control it was meant to explain. */}
      {requestUrl
        ? t('capabilities.needsApproval', { list })
        : t('capabilities.unavailable', { list })}
      {requestUrl && (
        <>
          {' '}
          <a href={requestUrl} target="_blank" rel="noopener noreferrer">
            {t('capabilities.requestAccess')} →
          </a>
        </>
      )}
    </p>
  );
}

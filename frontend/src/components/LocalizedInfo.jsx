import { useTranslation } from 'react-i18next';
import InfoPopover from './InfoPopover';

// The example is a code sample, not UI copy: the keys are the language codes the
// server accepts and the values illustrate what a Spanish/Catalan owner writes,
// so it reads the same whatever language the form itself is in.
const EXAMPLE = '{"es": "Las cosas de mamá", "ca": "Les coses de mama"}';
const TAGS_EXAMPLE = '{"es": "Juguetes", "ca": "Joguines"}';

/**
 * The quiet hint + (i) that tells an owner they may write one text per language
 * (O6). Rendered under the description in the thing/collection forms
 * (`variant="text"`, covering headline *and* description) and under the tag
 * editor (`variant="tags"`).
 *
 * Deliberately one hint per field group rather than one per input: the trick is
 * a single idea, and DESIGN §3 says remove what isn't necessary. It uses the
 * established `.info-popover-row` pattern (help line left, icon flush right, so
 * the `right: 0`-anchored panel stays inside the viewport).
 *
 * Props: `id` (the popover panel's id), `variant` (`text` | `tags` | `policy`).
 * `policy` (D5, 2026-08) is the deposit policy in RentalRulesFields — its own
 * variant rather than reusing `text`, since that hint specifically names
 * "the title or the description" and a deposit policy is neither.
 */

const VARIANT_KEYS = {
  text: { hint: 'localized.hint', infoBody: 'localized.infoBody', example: EXAMPLE },
  tags: { hint: 'localized.tagsHint', infoBody: 'localized.tagsInfoBody', example: TAGS_EXAMPLE },
  policy: { hint: 'localized.policyHint', infoBody: 'localized.policyInfoBody', example: EXAMPLE },
};

export default function LocalizedInfo({ id, variant = 'text' }) {
  const { t } = useTranslation();
  const keys = VARIANT_KEYS[variant];

  return (
    <div className="info-popover-row">
      <span className="localized-hint">{t(keys.hint)}</span>
      <InfoPopover id={id} title={t('localized.infoTitle')}>
        <p>{t(keys.infoBody)}</p>
        <code className="localized-example">{keys.example}</code>
        <p>{t('localized.infoFallback')}</p>
      </InfoPopover>
    </div>
  );
}

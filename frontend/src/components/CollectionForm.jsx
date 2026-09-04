import { Select, ToggleButton } from 'hds-react';
import { useTranslation } from 'react-i18next';
import { ALLOWED_TYPES } from '../constants/things';
import hdsLang from '../utils/hdsLang';
import useCapabilities, { isOfferable } from '../hooks/useCapabilities';
import ApprovalNotice from './ApprovalNotice';

/**
 * The shared identity cluster of the Create and Edit collection forms — the part
 * that stays visible above the "More options" accordion (O1): the visibility
 * toggle and the allowed-thing-types multi-select (its "pick at least one" rule
 * must never hide).
 *
 * The rental-rules fields that used to trail this cluster now live in
 * `RentalRulesFields` (rendered by the pages inside the accordion).
 *
 * Controlled: every value + setter is owned by the page; this component only
 * renders the cluster. `idPrefix` is `create-collection`
 * or `edit-collection`; `theeemeColor01` is the theeeme `color_01` token name.
 */
export default function CollectionForm({
  idPrefix,
  allowedThingTypes,
  setAllowedThingTypes,
  visibility = 'PRIVATE',
  setVisibility = () => {},
  allowProposals = true,
  setAllowProposals = () => {},
  errors,
  theeemeColor01,
}) {
  const { t, i18n } = useTranslation();
  const capabilities = useCapabilities();
  const toggleTheme = theeemeColor01
    ? { '--toggle-button-color': `var(--color-${theeemeColor01})` }
    : undefined;

  // Every type the product has, labelled — what the Select would offer if
  // nothing were withheld. `ApprovalNotice` diffs this against the deployment's
  // capabilities to name what is missing.
  const typeCatalogue = ALLOWED_TYPES.map((v) => ({ label: t('types.' + v), value: v }));
  // Narrowed the same way `CollectionModeField` narrows `collection_modes`: a
  // type this account may not offer here is left off the list rather than
  // shown selectable and refused at submit. A type already on the collection's
  // own allowlist stays offered even if the policy no longer allows it — the
  // server only judges a *change*, and hiding it here would save a wrong list.
  const allowedTypesOptions = typeCatalogue.filter(
    (opt) =>
      isOfferable(capabilities, 'thing_types', opt.value) || allowedThingTypes.includes(opt.value)
  );

  return (
    <>
      <div className="toggle-left">
        <ToggleButton
          id={`${idPrefix}-visibility`}
          label={
            <>
              {t('visibility.publicLabel')}
              <br />
              <span
                style={{
                  fontSize: 'var(--fontsize-body-s)',
                  fontWeight: 400,
                  color: 'var(--color-black-70)',
                }}
              >
                {t('visibility.publicHelper')}
              </span>
            </>
          }
          checked={visibility === 'PUBLIC'}
          onChange={(val) => setVisibility(val ? 'PRIVATE' : 'PUBLIC')}
          variant="inline"
          theme={toggleTheme}
        />
      </div>
      {/* Whether members may recommend guests. The owner still decides on every
          one — this is whether they are willing to be asked at all, which a
          group with a waiting list or an admission process may not be. Sits
          with visibility because both answer "who can get in here". */}
      <div className="toggle-left">
        <ToggleButton
          id={`${idPrefix}-allow-proposals`}
          label={
            <>
              {t('recommend.settingLabel')}
              <br />
              <span
                style={{
                  fontSize: 'var(--fontsize-body-s)',
                  fontWeight: 400,
                  color: 'var(--color-black-70)',
                }}
              >
                {t('recommend.settingHelper')}
              </span>
            </>
          }
          checked={allowProposals}
          onChange={(val) => setAllowProposals(!val)}
          variant="inline"
          theme={toggleTheme}
        />
      </div>
      <div>
        <Select
          multiSelect
          id={`${idPrefix}-allowed-thing-types`}
          texts={{
            label: t('createCollection.allowedTypesLabel'),
            placeholder: t('createCollection.allowedTypesPlaceholder'),
            assistive: (() => {
              return t('createCollection.allowedTypesHelper');
            })(),
            error: errors.allowedThingTypes,
            language: hdsLang(i18n.language),
          }}
          options={allowedTypesOptions}
          value={allowedThingTypes.map((v) => ({
            label: t('types.' + v),
            value: v,
          }))}
          onChange={(opts) => setAllowedThingTypes(opts.map((o) => o.value))}
          invalid={!!errors.allowedThingTypes}
        />
        <ApprovalNotice kind="thing_types" catalogue={typeCatalogue} />
      </div>
    </>
  );
}

import { Select, TextArea } from 'hds-react';
import { useTranslation } from 'react-i18next';
import {
  RENTAL_DURATION_PRESETS,
  WEEKDAY_VALUES,
  durationLabel,
  weekdayLabel,
  weekdayNarrow,
} from '../utils/rental';
import LocalizedInfo from './LocalizedInfo';
import { localizedCounter } from '../utils/localized';

/**
 * The rental-rules fields (#7) for a collection that lends or rents items: the
 * fixed-durations multi-select plus the pickup/return weekday chip row.
 *
 * Extracted from CollectionForm so it can live inside the collection form's
 * "More options" accordion (O1) while the identity cluster stays visible.
 * Rendered for every collection: the rules only bite on LEND/RENT things, and
 * leaving them empty is the "no fixed durations" default.
 *
 * Controlled: value + setter owned by the page. `idPrefix` is
 * `create-collection` / `edit-collection`; `theeemeColor01` is the theeeme
 * `color_01` token name (the selected weekday chip's fill).
 *
 * `depositPolicy` (D5, 2026-08) rides along here rather than getting its own
 * component: it is the same class of statement as the duration/weekday rules
 * — how deposits work in this group — even though the amount itself lives on
 * each thing. Localizable like every other owner text (`LocalizedInfo
 * variant="policy"`).
 */
export default function RentalRulesFields({
  idPrefix,
  rentalDurations = [],
  setRentalDurations = () => {},
  rentalWeekdays = [],
  setRentalWeekdays = () => {},
  depositPolicy = '',
  setDepositPolicy = () => {},
  theeemeColor01,
}) {
  const { t, i18n } = useTranslation();

  return (
    <>
      <Select
        multiSelect
        id={`${idPrefix}-rental-durations`}
        texts={{
          label: t('rental.durationsLabel'),
          placeholder: t('rental.durationsPlaceholder'),
          assistive: t('rental.durationsHelper'),
          language: 'en',
        }}
        options={RENTAL_DURATION_PRESETS.map((p) => ({ label: t(p.key), value: String(p.days) }))}
        value={rentalDurations.map((d) => ({ label: durationLabel(d, t), value: String(d) }))}
        onChange={(opts) =>
          setRentalDurations(opts.map((o) => Number(o.value)).sort((a, b) => a - b))
        }
      />
      <div className="weekday-field">
        <p className="weekday-field-label" id={`${idPrefix}-rental-weekdays-label`}>
          {t('rental.weekdaysLabel')}
        </p>
        <div
          className="weekday-chips"
          role="group"
          aria-labelledby={`${idPrefix}-rental-weekdays-label`}
        >
          {WEEKDAY_VALUES.map((w) => {
            const selected = rentalWeekdays.includes(w);
            const full = weekdayLabel(w, i18n.language);
            return (
              <button
                key={w}
                type="button"
                className={`weekday-chip${selected ? ' selected' : ''}`}
                aria-pressed={selected}
                aria-label={full}
                title={full}
                onClick={() =>
                  setRentalWeekdays(
                    selected
                      ? rentalWeekdays.filter((x) => x !== w)
                      : [...rentalWeekdays, w].sort((a, b) => a - b)
                  )
                }
                style={
                  selected && theeemeColor01
                    ? {
                        backgroundColor: `var(--color-${theeemeColor01})`,
                        borderColor: `var(--color-${theeemeColor01})`,
                        color: 'var(--color-white)',
                      }
                    : undefined
                }
              >
                {weekdayNarrow(w, i18n.language)}
              </button>
            );
          })}
        </div>
        <p className="weekday-field-helper">{t('rental.weekdaysHelper')}</p>
      </div>
      {/* Empty by default, never suggested (DESIGN §6 — no dark pattern nudges
          a group towards deposits) and its own field, not folded into the
          duration/weekday cluster's copy: this is prose an owner writes, those
          are structured choices. A static paragraph carries the explanation —
          the TextArea's own helperText is the per-language counter, same slot
          every other localizable field uses it for. */}
      <p className="weekday-field-helper">{t('rental.depositPolicyHelper')}</p>
      <TextArea
        id={`${idPrefix}-deposit-policy`}
        label={t('rental.depositPolicyLabel')}
        value={depositPolicy}
        onChange={(e) => setDepositPolicy(e.target.value)}
        helperText={localizedCounter(depositPolicy, 256).text}
      />
      <LocalizedInfo id={`${idPrefix}-deposit-policy-localized-info`} variant="policy" />
    </>
  );
}

import { NumberInput } from 'hds-react';
import { useTranslation } from 'react-i18next';
import { WEEKDAY_VALUES, weekdayLabel, weekdayNarrow } from '../utils/rental';

/**
 * The rules a reservations collection's owner sets: how many days a member may
 * book the space for in one go, and which weekdays it is open for reservations.
 *
 * Shown (in the "More options" accordion) *instead of* `RentalRulesFields` when
 * the collection is a reservations collection — `allowed_thing_types` is exactly
 * `["RESERVE_THING"]`. It reuses the same `rental_weekdays` state the rental
 * rules use (the backend reuses the column), and the same weekday chip markup.
 *
 * Controlled: value + setter owned by the page. `idPrefix` is
 * `create-collection` / `edit-collection`; `theeemeColor01` fills the selected
 * chip.
 */
export default function ReservationRulesFields({
  idPrefix,
  reservationMaxDays = 1,
  setReservationMaxDays = () => {},
  reservationHorizonDays = 90,
  setReservationHorizonDays = () => {},
  rentalWeekdays = [],
  setRentalWeekdays = () => {},
  theeemeColor01,
}) {
  const { t, i18n } = useTranslation();

  return (
    <>
      <NumberInput
        id={`${idPrefix}-reservation-max-days`}
        label={t('reservation.maxDaysLabel')}
        helperText={t('reservation.maxDaysHelper')}
        min={1}
        max={7}
        step={1}
        value={reservationMaxDays}
        onChange={(e) => {
          const n = Number(e.target.value);
          setReservationMaxDays(Number.isFinite(n) ? Math.min(7, Math.max(1, n)) : 1);
        }}
      />
      <NumberInput
        id={`${idPrefix}-reservation-horizon-days`}
        label={t('reservation.horizonLabel')}
        helperText={t('reservation.horizonHelper')}
        min={1}
        max={365}
        step={1}
        value={reservationHorizonDays}
        onChange={(e) => {
          const n = Number(e.target.value);
          setReservationHorizonDays(Number.isFinite(n) ? Math.min(365, Math.max(1, n)) : 90);
        }}
      />
      <div className="weekday-field">
        <p className="weekday-field-label" id={`${idPrefix}-reservation-weekdays-label`}>
          {t('reservation.weekdaysLabel')}
        </p>
        <div
          className="weekday-chips"
          role="group"
          aria-labelledby={`${idPrefix}-reservation-weekdays-label`}
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
        <p className="weekday-field-helper">{t('reservation.weekdaysHelper')}</p>
      </div>
    </>
  );
}

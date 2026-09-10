import { NumberInput } from 'hds-react';
import { useTranslation } from 'react-i18next';
import WeekdayChips from './WeekdayChips';

/**
 * The rules a reservations collection's owner sets: how many days a member may
 * book the space for in one go, how far ahead they may book, and which weekdays
 * it is open for reservations.
 *
 * Shown (in the "More options" accordion) *instead of* `RentalRulesFields` when
 * the collection is a reservations collection — `allowed_thing_types` is exactly
 * `["RESERVE_THING"]`. It reuses the same `rental_weekdays` state the rental
 * rules use (the backend reuses the column), and the same `WeekdayChips` row.
 *
 * Controlled: value + setter owned by the page. `idPrefix` is
 * `create-collection` / `edit-collection`; `theeemeColor01` / `theeemeColor06`
 * are the theeeme token names for a selected weekday chip (fill + text — see
 * `WeekdayChips`).
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
  theeemeColor06,
}) {
  const { t } = useTranslation();

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
      <WeekdayChips
        labelId={`${idPrefix}-reservation-weekdays-label`}
        labelKey="reservation.weekdaysLabel"
        helperKey="reservation.weekdaysHelper"
        weekdays={rentalWeekdays}
        setWeekdays={setRentalWeekdays}
        color01={theeemeColor01}
        color06={theeemeColor06}
      />
    </>
  );
}

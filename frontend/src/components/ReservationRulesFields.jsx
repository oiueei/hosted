import { useEffect, useState } from 'react';
import { NumberInput } from 'hds-react';
import { useTranslation } from 'react-i18next';
import WeekdayChips from './WeekdayChips';

/**
 * One bounded whole-number field. HDS `NumberInput` is controlled, so a field
 * bound straight to `Math.min(max, Math.max(min, n))` snaps to the bound on
 * every keystroke — you cannot clear "3" to type "5", and an empty field jumps
 * to 1. This keeps a local draft string so the field can be emptied or briefly
 * hold an out-of-range value while editing, and clamps once, on blur. The parent
 * only ever hears a valid number, and only when it actually changes.
 */
function BoundedDayInput({ id, label, helperText, min, max, fallback, value, onChange }) {
  const [draft, setDraft] = useState(String(value));
  // Re-sync when the value arrives from outside — e.g. the Edit form finishing
  // its load. Our own commits set `draft` first, so this is then a no-op.
  useEffect(() => {
    setDraft(String(value));
  }, [value]);

  const commit = () => {
    const n = Math.round(Number(draft));
    const fixed =
      draft.trim() !== '' && Number.isFinite(n) ? Math.min(max, Math.max(min, n)) : fallback;
    setDraft(String(fixed));
    if (fixed !== value) onChange(fixed);
  };

  return (
    <NumberInput
      id={id}
      label={label}
      helperText={helperText}
      min={min}
      max={max}
      step={1}
      value={draft === '' ? '' : Number(draft)}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={commit}
    />
  );
}

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
      <BoundedDayInput
        id={`${idPrefix}-reservation-max-days`}
        label={t('reservation.maxDaysLabel')}
        helperText={t('reservation.maxDaysHelper')}
        min={1}
        max={7}
        fallback={1}
        value={reservationMaxDays}
        onChange={setReservationMaxDays}
      />
      <BoundedDayInput
        id={`${idPrefix}-reservation-horizon-days`}
        label={t('reservation.horizonLabel')}
        helperText={t('reservation.horizonHelper')}
        min={1}
        max={365}
        fallback={90}
        value={reservationHorizonDays}
        onChange={setReservationHorizonDays}
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

import { useEffect, useState } from 'react';
import { NumberInput, RadioButton, SelectionGroup } from 'hds-react';
import { useTranslation } from 'react-i18next';
import WeekdayChips from './WeekdayChips';
import OpeningHoursField from './OpeningHoursField';

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
 * The rules a reservations collection's owner sets. Two units, never both
 * (`Collection.reservation_unit`): **DAY** books whole days (how many in one
 * go, which weekdays are open); **HOUR** books a slot within a weekly opening
 * schedule (the shortest/longest slot in minutes, the schedule itself). How
 * far ahead a member may book and the active-reservations cap apply to either
 * unit, so they sit above the split.
 *
 * Shown (in the "More options" accordion) *instead of* `RentalRulesFields`
 * when the collection is a reservations collection — `allowed_thing_types` is
 * exactly `["RESERVE_THING"]`. DAY mode reuses the same `rental_weekdays`
 * state the rental rules use (the backend reuses the column) and the same
 * `WeekdayChips` row.
 *
 * Controlled: value + setter owned by the page. `idPrefix` is
 * `create-collection` / `edit-collection`; `theeemeColor01` / `theeemeColor06`
 * are the theeeme token names for a selected weekday chip (fill + text — see
 * `WeekdayChips`).
 *
 * **The unit radios are two static options, not a `.map()` over caller-owned
 * data** — unlike `CollectionModeField`'s two HDS `SelectionGroup` quirks
 * (frontend/CLAUDE.md), which exist for a *dynamic* option list. Kept the
 * same shape anyway (a flat array of `id`-carrying wrapper `div`s) since it's
 * the one proven not to trip either quirk in this codebase.
 */
export default function ReservationRulesFields({
  idPrefix,
  reservationUnit = 'DAY',
  setReservationUnit = () => {},
  reservationMaxDays = 1,
  setReservationMaxDays = () => {},
  reservationHorizonDays = 90,
  setReservationHorizonDays = () => {},
  reservationMaxActivePerMember = 10,
  setReservationMaxActivePerMember = () => {},
  reservationMinMinutes = 60,
  setReservationMinMinutes = () => {},
  reservationMaxMinutes = 180,
  setReservationMaxMinutes = () => {},
  openingHours = {},
  setOpeningHours = () => {},
  rentalWeekdays = [],
  setRentalWeekdays = () => {},
  theeemeColor01,
  theeemeColor06,
}) {
  const { t } = useTranslation();

  const unitOptions = [
    { value: 'DAY', label: t('reservation.unitDay') },
    { value: 'HOUR', label: t('reservation.unitHour') },
  ].map((opt) => {
    const id = `${idPrefix}-reservation-unit-${opt.value.toLowerCase()}`;
    return (
      <div key={id} id={`${id}-option`}>
        <RadioButton
          id={id}
          name={`${idPrefix}-reservation-unit`}
          value={opt.value}
          label={opt.label}
          checked={reservationUnit === opt.value}
          onChange={() => setReservationUnit(opt.value)}
        />
      </div>
    );
  });

  return (
    <>
      <SelectionGroup label={t('reservation.unitLabel')}>{unitOptions}</SelectionGroup>
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
      <BoundedDayInput
        id={`${idPrefix}-reservation-max-active`}
        label={t('reservation.maxActiveLabel')}
        helperText={t('reservation.maxActiveHelper')}
        min={1}
        max={50}
        fallback={10}
        value={reservationMaxActivePerMember}
        onChange={setReservationMaxActivePerMember}
      />
      {reservationUnit === 'HOUR' ? (
        <>
          <BoundedDayInput
            id={`${idPrefix}-reservation-min-minutes`}
            label={t('reservation.minMinutesLabel')}
            helperText={t('reservation.minMinutesHelper')}
            min={1}
            max={720}
            fallback={60}
            value={reservationMinMinutes}
            onChange={setReservationMinMinutes}
          />
          <BoundedDayInput
            id={`${idPrefix}-reservation-max-minutes`}
            label={t('reservation.maxMinutesLabel')}
            helperText={t('reservation.maxMinutesHelper')}
            min={1}
            max={720}
            fallback={180}
            value={reservationMaxMinutes}
            onChange={setReservationMaxMinutes}
          />
          <OpeningHoursField
            id={`${idPrefix}-opening-hours`}
            value={openingHours}
            onChange={setOpeningHours}
          />
        </>
      ) : (
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
      )}
    </>
  );
}

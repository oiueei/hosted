import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  displayToIso,
  parseLocalDate,
  formatHM,
  parseHM,
  dayBlocks,
  dayBookings,
  durationOptions,
  freeStartTimes,
  earliestStartMinutes,
  isHourlyPickupDisabled,
} from '../utils/rental';
import { optionPickerFocusId } from '../utils/optionPicker';

/**
 * The choices of an HOUR-unit reservation: day → duration → start time, in that
 * order (unlike the DAY-unit flow, which picks the length first). Each step's
 * options depend on the previous one, computed fresh from the thing's opening hours
 * and its fetched calendar — the same pure helpers the backend's own
 * `Collection.day_opening_blocks` / `reservation_hour_violation` mirror.
 *
 * `startDate` is the page's pickup date in the display format; `blockedPeriods` is
 * the fetched calendar. For a thing that is not an hourly reservation every
 * derived value is empty and nothing here does anything.
 */
export default function useHourlyReservation({ thing, startDate, blockedPeriods }) {
  const { t } = useTranslation();
  // A duration-option key (its minutes, e.g. '30') and a chosen "HH:MM" start —
  // kept apart from the page's day-count `duration`, since the two are never both
  // meaningful for the same thing.
  const [duration, setDuration] = useState('');
  const [startTime, setStartTime] = useState('');

  const isHourly = thing?.type === 'RESERVE_THING' && thing?.reservation_unit === 'HOUR';
  const closedDates = thing?.closed_dates || [];
  const openingHours = thing?.opening_hours || {};
  const minMinutes = thing?.reservation_min_minutes || 60;
  const maxMinutes = thing?.reservation_max_minutes || 180;
  const pickupDisabled = (date) =>
    isHourlyPickupDisabled(date, { openingHours, closedDates, blockedPeriods, minMinutes });
  const selectedIso = displayToIso(startDate);
  const blocksForSelectedDay =
    isHourly && selectedIso ? dayBlocks(openingHours, parseLocalDate(selectedIso)) : [];
  const bookingsForSelectedDay =
    isHourly && selectedIso
      ? dayBookings(blockedPeriods, selectedIso)
      : { wholeDay: false, ranges: [] };
  const durationChoices = isHourly ? durationOptions(minMinutes, maxMinutes) : [];
  const chosenDurationOption = durationChoices.find((o) => o.key === duration);
  // For today, only starts not yet passed (by the browser's clock) — see
  // `earliestStartMinutes`. Recomputed every render, so a start that passes
  // while the page sits open drops out of the list...
  const startTimeChoices = chosenDurationOption
    ? freeStartTimes(
        blocksForSelectedDay,
        chosenDurationOption.minutes,
        bookingsForSelectedDay,
        minMinutes,
        earliestStartMinutes(selectedIso)
      )
    : [];
  // ...and out of the selection too: a start the reader picked before it
  // passed is no longer one this page will send.
  const chosenStartTime = startTimeChoices.includes(startTime) ? startTime : '';
  // What a Reserve click is still missing, once a day is picked (a missing day is
  // the DateInput's own error). No start time is only "missing" when there were
  // some to choose from — with none, the "no start times" notice already says to
  // pick a shorter duration.
  const durationMissing = isHourly && !!selectedIso && !chosenDurationOption;
  const startTimeMissing =
    isHourly && !!chosenDurationOption && startTimeChoices.length > 0 && !chosenStartTime;
  const durationOptionLabel = (opt) => {
    const hours = Math.floor(opt.minutes / 60);
    const minutes = opt.minutes % 60;
    if (hours === 0) return t('reservation.minutes', { count: minutes });
    if (minutes === 0) return t('reservation.hours', { count: hours });
    return t('reservation.hoursAndMinutes', { hours, minutes });
  };
  // Radios for a handful, a dropdown past OptionPicker's RADIO_MAX — a short
  // minimum turns both lists long (48 start times at 15 minutes over 12 hours).
  const durationPickerOptions = durationChoices.map((opt) => ({
    value: opt.key,
    label: durationOptionLabel(opt),
  }));
  const startTimePickerOptions = startTimeChoices.map((hm) => ({ value: hm, label: hm }));

  // A Reserve click that can't be sent used to do nothing visible: the radio
  // groups had no error state, unlike the DAY flow's Select (found in review,
  // 2026-09-18 — and more reachable once a start that passes while the page sits
  // open drops out of the selection on its own). The group now shows HDS's error
  // text, and focus moves to its first option, which reads the question out —
  // HDS links that error text to nothing.
  const focusMissingChoice = () => {
    const first = durationMissing
      ? optionPickerFocusId('reservation-duration', durationPickerOptions)
      : startTimeMissing
        ? optionPickerFocusId('reservation-start-time', startTimePickerOptions)
        : null;
    if (first) document.getElementById(first)?.focus();
  };

  return {
    isHourly,
    pickupDisabled,
    selectedIso,
    duration,
    chosenDurationOption,
    chosenStartTime,
    startTimeChoices,
    durationMissing,
    startTimeMissing,
    durationPickerOptions,
    startTimePickerOptions,
    chooseDuration: (key) => {
      setDuration(key);
      setStartTime('');
    },
    chooseStartTime: setStartTime,
    /** The day changed: what was chosen for the old one no longer stands. */
    reset: () => {
      setDuration('');
      setStartTime('');
    },
    focusMissingChoice,
    /** The slot to book, once all three parts are chosen, else `null`. */
    slot: () =>
      selectedIso && chosenDurationOption && chosenStartTime
        ? {
            date: selectedIso,
            start: chosenStartTime,
            end: formatHM(parseHM(chosenStartTime) + chosenDurationOption.minutes),
          }
        : null,
  };
}

import { useTranslation } from 'react-i18next';
import { DateInput, Notification } from 'hds-react';
import {
  isoToDisplay,
  daysFromToday,
  startOfToday,
  reservationHorizonDays,
  DISPLAY_DATE_FORMAT,
} from '../../utils/rental';
import hdsLang from '../../utils/hdsLang';
import OptionPicker from '../OptionPicker';
import StatusRegion from '../StatusRegion';

/**
 * A reservation by the hour: the day, then how long, then when it starts. `hourly`
 * is `useHourlyReservation`'s answer, which owns the choices; `children` is the
 * project note, which sits last inside the same block.
 */
export default function HourlyReservationFields({
  thing,
  hourly,
  startDate,
  onStartDate,
  attempted,
  children,
}) {
  const { t, i18n } = useTranslation();
  const horizonDays = reservationHorizonDays(thing);
  const slot = hourly.slot();

  return (
    <div className="summary-grid section-mt">
      <DateInput
        id="reservation-pickup-date-hourly"
        label={t('reservation.pickupLabelHourly')}
        helperText={t('reservation.pickupHelperHourly')}
        value={startDate}
        onChange={(value) => {
          onStartDate(value);
          hourly.reset();
        }}
        dateFormat={DISPLAY_DATE_FORMAT}
        language={hdsLang(i18n.language)}
        openButtonAriaLabel={t('datePicker.open')}
        selectButtonLabel={t('datePicker.select')}
        closeButtonLabel={t('datePicker.close')}
        required
        invalid={attempted && !startDate}
        errorText={attempted && !startDate ? t('request.startRequired') : undefined}
        minDate={startOfToday()}
        maxDate={daysFromToday(horizonDays)}
        dateOutsideRangeErrorText={t('reservation.dateRange', { days: horizonDays })}
        isDateDisabledBy={hourly.pickupDisabled}
        malformedDateErrorText={t('request.dateOverlap')}
      />
      {hourly.selectedIso && (
        <>
          <div className="spacer-xxxs" />
          <OptionPicker
            idPrefix="reservation-duration"
            name="reservation-duration"
            label={t('reservation.durationLabelHourly')}
            placeholder={t('rental.chooseDurationPlaceholder')}
            options={hourly.durationPickerOptions}
            value={hourly.duration}
            onChange={hourly.chooseDuration}
            errorText={
              attempted && hourly.durationMissing ? t('rental.durationRequired') : undefined
            }
          />
        </>
      )}
      {hourly.duration && hourly.startTimeChoices.length > 0 && (
        <>
          <div className="spacer-xxxs" />
          <OptionPicker
            idPrefix="reservation-start-time"
            name="reservation-start-time"
            label={t('reservation.startTimeLabel')}
            placeholder={t('reservation.startTimePlaceholder')}
            options={hourly.startTimePickerOptions}
            value={hourly.chosenStartTime}
            onChange={hourly.chooseStartTime}
            errorText={
              attempted && hourly.startTimeMissing ? t('reservation.startTimeRequired') : undefined
            }
          />
        </>
      )}
      {/* Rendered unconditionally (StatusRegion), the conditional stays
          inside it — see StatusRegion.jsx's own note. A live region
          only announces a change made *inside a region that already
          existed*: gating the Notification itself behind the chosen duration
          (as this used to) meant the reader picking a duration with no
          free start left that day heard nothing at all — the
          Notification was never inside a live region, since it didn't
          exist yet either (WCAG 4.1.3, found in review 2026-09-18). */}
      <StatusRegion>
        {/* The slot this Reserve will book, once all three parts are
            picked — the end time is never shown anywhere else, and the
            reservation auto-confirms. In the live region, so choosing a
            start time reads the whole slot back. */}
        {slot && (
          <p className="thing-card-meta" style={{ marginTop: 'var(--spacing-2-xs)' }}>
            {t('reservation.slotSummary', {
              date: isoToDisplay(slot.date),
              start: slot.start,
              end: slot.end,
            })}
          </p>
        )}
        {hourly.duration && hourly.startTimeChoices.length === 0 && (
          <>
            <div className="spacer-xxxs" />
            {/* `notificationAriaLabel` distinguishes this landmark from
                the availability Notification above, which is always
                mounted alongside it here — two HDS Notifications share
                the same default aria-label ("Notification"), which
                axe's landmark-unique rule (correctly) flags once both
                are on screen at once (found by the new axe coverage
                for this page, 2026-09-18). */}
            <Notification
              type="info"
              size="small"
              label={t('reservation.noStartTimesLabel')}
              notificationAriaLabel={t('reservation.noStartTimesLabel')}
            >
              {t('reservation.noStartTimesForDuration')}
            </Notification>
          </>
        )}
      </StatusRegion>
      <div className="spacer-xxxs" />
      {children}
    </div>
  );
}

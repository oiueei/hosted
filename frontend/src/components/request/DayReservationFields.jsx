import { useTranslation } from 'react-i18next';
import { DateInput, Select } from 'hds-react';
import {
  isoToDisplay,
  displayToIso,
  derivedReturnDate,
  daysFromToday,
  startOfToday,
  reservationHorizonDays,
  reservationMaxDays,
  DISPLAY_DATE_FORMAT,
} from '../../utils/rental';
import hdsLang from '../../utils/hdsLang';

/**
 * A reservation by the day: a pickup date and, when the collection allows more
 * than one day, a length of 1..`reservation_max_days`. `children` is the project
 * note, which sits last inside the same block.
 *
 * `onDuration` receives the chosen length (`''` when it is cleared); the page
 * clears the pickup date with it, since the dates that are open depend on it.
 */
export default function DayReservationFields({
  thing,
  chosenDuration,
  onDuration,
  startDate,
  onStartDate,
  attempted,
  pickupDisabled,
  children,
}) {
  const { t, i18n } = useTranslation();
  // The Select is omitted (length fixed to 1) when the collection caps it at 1.
  const reservationMax = reservationMaxDays(thing);
  const reservationLengths = Array.from({ length: reservationMax }, (_, i) => i + 1);
  const horizonDays = reservationHorizonDays(thing);

  return (
    <div className="summary-grid section-mt">
      {reservationMax > 1 && (
        <>
          <Select
            id="reservation-duration"
            texts={{
              label: t('reservation.durationLabel'),
              placeholder: t('rental.chooseDurationPlaceholder'),
              error: attempted && !chosenDuration ? t('rental.durationRequired') : undefined,
              language: hdsLang(i18n.language),
            }}
            options={reservationLengths.map((d) => ({
              label: t('reservation.days', { count: d }),
              value: String(d),
            }))}
            value={
              chosenDuration
                ? [
                    {
                      label: t('reservation.days', { count: Number(chosenDuration) }),
                      value: chosenDuration,
                    },
                  ]
                : []
            }
            onChange={(opts) => onDuration(opts.length ? opts[0].value : '')}
            invalid={attempted && !chosenDuration}
          />
          <div className="spacer-xxxs" />
        </>
      )}
      <DateInput
        id="reservation-pickup-date"
        label={t('reservation.pickupLabel')}
        helperText={t('reservation.pickupHelper')}
        value={startDate}
        onChange={(value) => onStartDate(value)}
        dateFormat={DISPLAY_DATE_FORMAT}
        language={hdsLang(i18n.language)}
        openButtonAriaLabel={t('datePicker.open')}
        selectButtonLabel={t('datePicker.select')}
        closeButtonLabel={t('datePicker.close')}
        required
        disabled={!chosenDuration}
        invalid={attempted && !startDate}
        errorText={attempted && !startDate ? t('request.startRequired') : undefined}
        minDate={startOfToday()}
        maxDate={daysFromToday(horizonDays)}
        dateOutsideRangeErrorText={t('reservation.dateRange', { days: horizonDays })}
        isDateDisabledBy={pickupDisabled}
        malformedDateErrorText={t('request.dateOverlap')}
      />
      {/* The span the member is about to book, once both parts are set
          — the reservation auto-confirms, so there is no owner step
          that would catch a wrong end date. Shown only when the length
          is more than a day (a 1-day slot IS the pickup date). */}
      {Number(chosenDuration) > 1 && displayToIso(startDate) && (
        <p className="thing-card-meta" style={{ marginTop: 'var(--spacing-2-xs)' }}>
          {t('reservation.dateSummary', {
            start: startDate,
            end: isoToDisplay(
              derivedReturnDate(displayToIso(startDate), Number(chosenDuration) - 1)
            ),
          })}
        </p>
      )}
      <div className="spacer-xxxs" />
      {children}
    </div>
  );
}

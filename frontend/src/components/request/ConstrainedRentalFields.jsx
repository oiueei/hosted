import { useTranslation } from 'react-i18next';
import { DateInput, Select } from 'hds-react';
import {
  durationLabel,
  isoToDisplay,
  displayToIso,
  derivedReturnDate,
  daysFromToday,
  startOfToday,
  DISPLAY_DATE_FORMAT,
} from '../../utils/rental';
import hdsLang from '../../utils/hdsLang';

/**
 * A rental whose collection fixes the lengths: the renter picks one, then a
 * pickup date, and the return is derived as pickup + length.
 *
 * `onDuration` receives the chosen length (`''` when it is cleared); the page
 * clears the pickup date with it, since the dates that are open depend on it.
 */
export default function ConstrainedRentalFields({
  durations,
  chosenDuration,
  onDuration,
  startDate,
  onStartDate,
  attempted,
  pickupDisabled,
}) {
  const { t, i18n } = useTranslation();

  return (
    <div className="summary-grid section-mt">
      <Select
        id="request-duration"
        texts={{
          label: t('rental.chooseDuration'),
          placeholder: t('rental.chooseDurationPlaceholder'),
          error: attempted && !chosenDuration ? t('rental.durationRequired') : undefined,
          language: hdsLang(i18n.language),
        }}
        options={durations.map((d) => ({
          label: durationLabel(d, t),
          value: String(d),
        }))}
        value={
          chosenDuration
            ? [{ label: durationLabel(Number(chosenDuration), t), value: chosenDuration }]
            : []
        }
        onChange={(opts) => onDuration(opts.length ? opts[0].value : '')}
        invalid={attempted && !chosenDuration}
      />
      <div className="spacer-xxxs" />
      <DateInput
        id="request-pickup-date"
        label={t('rental.pickupLabel')}
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
        maxDate={daysFromToday(90)}
        dateOutsideRangeErrorText={t('request.dateRange')}
        isDateDisabledBy={pickupDisabled}
        malformedDateErrorText={t('request.dateOverlap')}
      />
      {chosenDuration && displayToIso(startDate) && (
        <p className="thing-card-meta" style={{ marginTop: 'var(--spacing-2-xs)' }}>
          {t('rental.returnBy', {
            date: isoToDisplay(derivedReturnDate(displayToIso(startDate), chosenDuration)),
          })}
        </p>
      )}
    </div>
  );
}

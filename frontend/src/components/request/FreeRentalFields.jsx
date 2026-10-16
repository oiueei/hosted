import { useTranslation } from 'react-i18next';
import { DateInput } from 'hds-react';
import { daysFromToday, startOfToday, DISPLAY_DATE_FORMAT } from '../../utils/rental';
import hdsLang from '../../utils/hdsLang';

/** A loan or rental with no fixed lengths: a pickup date and a return date. */
export default function FreeRentalFields({
  startDate,
  onStartDate,
  endDate,
  onEndDate,
  attempted,
  pickupBlocked,
  returnBlocked,
}) {
  const { t, i18n } = useTranslation();

  return (
    <div className="summary-grid section-mt">
      <DateInput
        id="request-start-date"
        label={t('request.startLabel')}
        value={startDate}
        onChange={(value) => onStartDate(value)}
        dateFormat={DISPLAY_DATE_FORMAT}
        language={hdsLang(i18n.language)}
        openButtonAriaLabel={t('datePicker.open')}
        selectButtonLabel={t('datePicker.select')}
        closeButtonLabel={t('datePicker.close')}
        required
        invalid={attempted && !startDate}
        errorText={attempted && !startDate ? t('request.startRequired') : undefined}
        minDate={startOfToday()}
        maxDate={daysFromToday(90)}
        dateOutsideRangeErrorText={t('request.dateRange')}
        isDateDisabledBy={pickupBlocked}
        malformedDateErrorText={t('request.dateOverlap')}
      />
      <div className="spacer-xxxs" />
      <DateInput
        id="request-end-date"
        label={t('request.endLabel')}
        value={endDate}
        onChange={(value) => onEndDate(value)}
        dateFormat={DISPLAY_DATE_FORMAT}
        language={hdsLang(i18n.language)}
        openButtonAriaLabel={t('datePicker.open')}
        selectButtonLabel={t('datePicker.select')}
        closeButtonLabel={t('datePicker.close')}
        required
        invalid={attempted && !endDate}
        errorText={attempted && !endDate ? t('request.endRequired') : undefined}
        minDate={startOfToday()}
        maxDate={daysFromToday(90)}
        dateOutsideRangeErrorText={t('request.dateRange')}
        isDateDisabledBy={returnBlocked}
        malformedDateErrorText={t('request.dateOverlap')}
      />
    </div>
  );
}

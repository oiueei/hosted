import { TextInput } from 'hds-react';
import { useTranslation } from 'react-i18next';

/**
 * The owner's holidays / one-off closures for a collection — a single line of
 * comma-separated `DD/MM/YYYY`. Stored as sorted ISO strings
 * (`Collection.closed_dates`); the backend parses this line, drops past dates
 * and caps the count. On those days no LEND/RENT pickup or return is offered,
 * and no RESERVE span may cross one.
 *
 * Controlled: `value` is the raw text, `onChange` gets the raw text. The pages
 * convert the loaded ISO list with `closedDatesToDisplay` and send the raw text
 * straight through.
 */
export default function ClosedDatesField({ id, value, onChange, error }) {
  const { t } = useTranslation();
  return (
    <TextInput
      id={id}
      label={t('closedDates.label')}
      helperText={t('closedDates.helper')}
      placeholder="25/12/2026, 26/12/2026"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      invalid={!!error}
      errorText={error}
      maxLength={800}
    />
  );
}

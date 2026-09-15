import { useEffect, useState } from 'react';
import { TextArea } from 'hds-react';
import { useTranslation } from 'react-i18next';

/**
 * The weekly opening-hours editor for an HOUR-unit reservations collection:
 * one raw-JSON `TextArea`, matching `Collection.opening_hours` exactly —
 * `{"0".."6": [["HH:MM","HH:MM"], ...]}`, Python weekday() numbering
 * (0=Mon…6=Sun) as string keys, a day absent or given `[]` closed. CA's own
 * call, after trying the per-day block editor this replaced: typing or
 * pasting the JSON directly is faster than clicking through seven fieldsets
 * for a schedule you already have written down somewhere.
 *
 * Local `draft` mirrors `BoundedDayInput`'s pattern — the owner can type a
 * momentarily unbalanced brace without the field fighting them — but unlike
 * that field (and unlike `ClosedDatesField`, which forwards its raw string
 * untouched), this one *must* parse on the way out: `opening_hours` is a
 * nested JSON object in the request body, not a string, so an unparseable
 * draft simply cannot become a valid `onChange` call. A parse failure keeps
 * the parent's last-known-good value and shows an inline error instead of
 * ever forwarding one — the deeper *shape* checks (day keys, HH:MM format,
 * overlap) still stay the backend's job, same as everywhere else in these
 * forms (`_validate_opening_hours`, surfaced as its own 400 via Toast).
 */
export default function OpeningHoursField({ id, value = {}, onChange = () => {} }) {
  const { t } = useTranslation();
  const [draft, setDraft] = useState(() => JSON.stringify(value));
  const [error, setError] = useState('');

  // Re-sync when the value arrives from outside — the Edit form finishing its
  // load, or our own commit below re-serialising what we just parsed.
  useEffect(() => {
    setDraft(JSON.stringify(value));
  }, [value]);

  const commit = () => {
    if (draft.trim() === '') {
      setError('');
      if (Object.keys(value).length) onChange({});
      return;
    }
    let parsed;
    try {
      parsed = JSON.parse(draft);
    } catch {
      setError(t('openingHours.invalidJson'));
      return;
    }
    if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
      setError(t('openingHours.invalidJson'));
      return;
    }
    setError('');
    onChange(parsed);
  };

  return (
    <TextArea
      id={id}
      label={t('openingHours.label')}
      helperText={t('openingHours.helper')}
      value={draft}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={commit}
      invalid={!!error}
      errorText={error}
    />
  );
}

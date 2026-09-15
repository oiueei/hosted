import { Button, TimeInput } from 'hds-react';
import { useTranslation } from 'react-i18next';
import { WEEKDAY_VALUES, weekdayLabel } from '../utils/rental';

const MAX_BLOCKS_PER_DAY = 4;

/**
 * The weekly opening-hours editor for an HOUR-unit reservations collection:
 * one row per weekday, each holding zero or more `[start, end]` time blocks
 * (a lunch-break gap is just a second block). Value/shape mirror the backend
 * exactly — `{"0".."6": [["HH:MM","HH:MM"], ...]}`, Python weekday numbering
 * (0=Mon…6=Sun) as string keys, same as `Collection.opening_hours` and
 * `_validate_opening_hours`.
 *
 * Deliberately unvalidated here, the same stance `ClosedDatesField` takes:
 * raw values in, raw values out. Sorting, overlap and start<end checks are
 * the backend's job (`_validate_opening_hours`); a bad edit surfaces as the
 * server's own 400 via Toast, same as everywhere else in these forms.
 *
 * Each weekday is a native `<fieldset>/<legend>` rather than an HDS
 * `SelectionGroup` — there are no radios here to trip its two quirks
 * (frontend/CLAUDE.md), just `TimeInput`s and buttons, so the plain
 * accessible grouping HTML already gives is enough.
 */
export default function OpeningHoursEditor({ idPrefix, value = {}, onChange = () => {} }) {
  const { t, i18n } = useTranslation();

  const blocksFor = (day) => value[String(day)] || [];

  const updateBlock = (day, index, which, newValue) => {
    const dayKey = String(day);
    const blocks = blocksFor(day).map((block, i) => {
      if (i !== index) return block;
      return which === 'start' ? [newValue, block[1]] : [block[0], newValue];
    });
    onChange({ ...value, [dayKey]: blocks });
  };

  const addBlock = (day) => {
    const dayKey = String(day);
    onChange({ ...value, [dayKey]: [...blocksFor(day), ['', '']] });
  };

  const removeBlock = (day, index) => {
    const dayKey = String(day);
    const blocks = blocksFor(day).filter((_, i) => i !== index);
    const next = { ...value };
    if (blocks.length) next[dayKey] = blocks;
    else delete next[dayKey];
    onChange(next);
  };

  return (
    <div className="opening-hours-editor">
      <p className="opening-hours-editor-label" id={`${idPrefix}-opening-hours-label`}>
        {t('openingHours.label')}
      </p>
      <p className="opening-hours-editor-helper">{t('openingHours.helper')}</p>
      {WEEKDAY_VALUES.map((day) => {
        const blocks = blocksFor(day);
        return (
          <fieldset key={day} className="opening-hours-day">
            <legend>{weekdayLabel(day, i18n.language)}</legend>
            {blocks.length === 0 && (
              <p className="opening-hours-closed">{t('openingHours.closed')}</p>
            )}
            {blocks.map((block, index) => {
              const startId = `${idPrefix}-oh-${day}-${index}-start`;
              const endId = `${idPrefix}-oh-${day}-${index}-end`;
              return (
                <div className="opening-hours-block" key={index}>
                  <TimeInput
                    id={startId}
                    label={t('openingHours.fromLabel')}
                    hoursLabel={t('openingHours.hoursLabel')}
                    minutesLabel={t('openingHours.minutesLabel')}
                    value={block[0]}
                    onChange={(e) => updateBlock(day, index, 'start', e.target.value)}
                  />
                  <TimeInput
                    id={endId}
                    label={t('openingHours.toLabel')}
                    hoursLabel={t('openingHours.hoursLabel')}
                    minutesLabel={t('openingHours.minutesLabel')}
                    value={block[1]}
                    onChange={(e) => updateBlock(day, index, 'end', e.target.value)}
                  />
                  <Button
                    variant="supplementary"
                    size="small"
                    iconStart={<span aria-hidden="true">✕</span>}
                    onClick={() => removeBlock(day, index)}
                  >
                    {t('openingHours.removeBlock')}
                  </Button>
                </div>
              );
            })}
            {blocks.length < MAX_BLOCKS_PER_DAY && (
              <Button variant="secondary" size="small" onClick={() => addBlock(day)}>
                {t('openingHours.addBlock')}
              </Button>
            )}
          </fieldset>
        );
      })}
    </div>
  );
}

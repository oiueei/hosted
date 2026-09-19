import { useTranslation } from 'react-i18next';
import { Select } from 'hds-react';
import RadioOptionGroup from './RadioOptionGroup';
import hdsLang from '../utils/hdsLang';
import { RADIO_MAX } from '../utils/optionPicker';

/**
 * One choice from a dynamic option list: a `RadioOptionGroup` for a handful, an
 * HDS `Select` past `RADIO_MAX`. The caller keeps one API either way — `value`
 * and `onChange` carry the option's `value`, never an HDS option object.
 *
 * `optionPickerFocusId` (utils/optionPicker.js) names the element to focus when
 * the choice is missing on submit.
 */
export default function OptionPicker({
  idPrefix,
  name,
  label,
  placeholder,
  options,
  value,
  onChange,
  errorText,
}) {
  const { i18n } = useTranslation();
  if (options.length <= RADIO_MAX) {
    return (
      <RadioOptionGroup
        idPrefix={idPrefix}
        name={name}
        label={label}
        options={options}
        value={value}
        onChange={onChange}
        errorText={errorText}
      />
    );
  }
  const selected = options.find((opt) => opt.value === value);
  return (
    <Select
      id={idPrefix}
      texts={{ label, placeholder, error: errorText, language: hdsLang(i18n.language) }}
      options={options}
      value={selected ? [selected] : []}
      onChange={(opts) => onChange(opts.length ? opts[0].value : '')}
      invalid={!!errorText}
    />
  );
}

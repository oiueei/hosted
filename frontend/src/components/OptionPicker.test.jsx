import { render, screen, fireEvent } from '@testing-library/react';
import { describe, test, expect, vi } from 'vitest';
import OptionPicker from './OptionPicker';
import { RADIO_MAX, optionPickerFocusId } from '../utils/optionPicker';

const options = (n) =>
  Array.from({ length: n }, (_, i) => ({ value: String(i + 1), label: `Option ${i + 1}` }));

const renderPicker = (n, props = {}) =>
  render(
    <OptionPicker
      idPrefix="pick"
      name="pick"
      label="Pick one"
      placeholder="Choose"
      options={options(n)}
      value=""
      onChange={() => {}}
      {...props}
    />
  );

describe('OptionPicker', () => {
  test(`up to ${RADIO_MAX} options stay radios`, () => {
    renderPicker(RADIO_MAX);
    expect(screen.getAllByRole('radio')).toHaveLength(RADIO_MAX);
    expect(screen.queryByRole('combobox')).toBeNull();
  });

  test('one more becomes a dropdown with the same label', () => {
    renderPicker(RADIO_MAX + 1);
    expect(screen.queryAllByRole('radio')).toHaveLength(0);
    expect(screen.getByRole('combobox', { name: /Pick one/ })).toBeInTheDocument();
  });

  test('the dropdown hands back the plain value, as the radios do', async () => {
    const onChange = vi.fn();
    renderPicker(RADIO_MAX + 1, { onChange });

    fireEvent.click(screen.getByRole('combobox', { name: /Pick one/ }));
    fireEvent.click(await screen.findByRole('option', { name: 'Option 9' }));

    expect(onChange).toHaveBeenLastCalledWith('9');
  });

  test('the focus target is the first radio, or the dropdown’s own trigger', () => {
    expect(optionPickerFocusId('pick', options(RADIO_MAX))).toBe('pick-1');
    expect(optionPickerFocusId('pick', options(RADIO_MAX + 1))).toBe('pick-main-button');

    renderPicker(RADIO_MAX + 1);
    expect(document.getElementById('pick-main-button')).toBe(
      screen.getByRole('combobox', { name: /Pick one/ })
    );
  });
});

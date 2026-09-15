import { render, screen, fireEvent } from '@testing-library/react';
import { describe, test, expect, vi } from 'vitest';
import OpeningHoursField from './OpeningHoursField';

// CA's own call: one raw-JSON TextArea instead of the per-day block editor it
// replaced — typing or pasting the schedule directly. It must still only ever
// hand the parent real JSON, never a string or a parse error, since
// opening_hours is a nested object in the request body.

function renderField(over = {}) {
  const onChange = vi.fn();
  const utils = render(
    <OpeningHoursField
      id="edit-collection-opening-hours"
      value={{}}
      onChange={onChange}
      {...over}
    />
  );
  return { ...utils, onChange };
}

const field = () => screen.getByLabelText('Weekly opening hours');

describe('OpeningHoursField', () => {
  test('shows the stored value serialised as JSON', () => {
    renderField({ value: { 0: [['10:00', '14:00']] } });
    expect(field()).toHaveValue(JSON.stringify({ 0: [['10:00', '14:00']] }));
  });

  test('valid JSON is parsed and handed to the parent on blur', () => {
    const { onChange } = renderField();
    const json = '{"0":[["10:00","14:00"],["16:00","20:00"]],"4":[["10:00","14:00"]]}';
    fireEvent.change(field(), { target: { value: json } });
    expect(onChange).not.toHaveBeenCalled(); // not yet — still typing
    fireEvent.blur(field());
    expect(onChange).toHaveBeenCalledWith({
      0: [
        ['10:00', '14:00'],
        ['16:00', '20:00'],
      ],
      4: [['10:00', '14:00']],
    });
  });

  test('malformed JSON shows an inline error and never reaches the parent', () => {
    const { onChange } = renderField();
    fireEvent.change(field(), { target: { value: '{"0": [["10:00"' } });
    fireEvent.blur(field());
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.getByText(/not valid JSON/)).toBeInTheDocument();
  });

  test('a JSON array (not an object) is rejected the same way', () => {
    const { onChange } = renderField();
    fireEvent.change(field(), { target: { value: '["not", "an", "object"]' } });
    fireEvent.blur(field());
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.getByText(/not valid JSON/)).toBeInTheDocument();
  });

  test('clearing the field commits an empty schedule', () => {
    const { onChange } = renderField({ value: { 0: [['10:00', '14:00']] } });
    fireEvent.change(field(), { target: { value: '' } });
    fireEvent.blur(field());
    expect(onChange).toHaveBeenCalledWith({});
  });

  test('fixing a previously invalid draft clears the error', () => {
    renderField();
    fireEvent.change(field(), { target: { value: 'not json at all' } });
    fireEvent.blur(field());
    expect(screen.getByText(/not valid JSON/)).toBeInTheDocument();

    fireEvent.change(field(), { target: { value: '{"0": [["10:00","14:00"]]}' } });
    fireEvent.blur(field());
    expect(screen.queryByText(/not valid JSON/)).toBeNull();
  });

  test('a value that changed from outside the component re-syncs the draft', () => {
    const { rerender, onChange } = renderField({ value: { 0: [['10:00', '14:00']] } });
    rerender(
      <OpeningHoursField
        id="edit-collection-opening-hours"
        value={{ 1: [['09:00', '13:00']] }}
        onChange={onChange}
      />
    );
    expect(field()).toHaveValue(JSON.stringify({ 1: [['09:00', '13:00']] }));
  });
});

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

  test('a same-content but new-reference value does NOT clobber an in-progress draft', () => {
    // The exact shape of `openingHours={form.opening_hours || {}}`: a parent
    // re-render (an unrelated field changing) hands down a fresh `{}` object
    // literal, identical in content to the one already synced but a different
    // reference. Keying the resync on the object reference instead of its
    // content would wipe whatever the owner is mid-typing (found in review,
    // 2026-09-18 — real data loss in a field people paste a whole schedule
    // into, though unreachable today since both call sites pass a stable
    // `useState` object).
    const { rerender, onChange } = renderField({ value: {} });
    fireEvent.change(field(), { target: { value: '{"0": [["09:00","17:0' } });
    expect(field()).toHaveValue('{"0": [["09:00","17:0');

    rerender(
      <OpeningHoursField id="edit-collection-opening-hours" value={{}} onChange={onChange} />
    );

    expect(field()).toHaveValue('{"0": [["09:00","17:0');
  });

  test('a same-content but new-reference value still lets a later real external change through', () => {
    // The fix above must not become "never resync again" — a genuine content
    // change from outside (the Edit form finishing its load) still has to land.
    const { rerender, onChange } = renderField({ value: {} });
    rerender(
      <OpeningHoursField id="edit-collection-opening-hours" value={{}} onChange={onChange} />
    );
    rerender(
      <OpeningHoursField
        id="edit-collection-opening-hours"
        value={{ 2: [['09:00', '17:00']] }}
        onChange={onChange}
      />
    );

    expect(field()).toHaveValue(JSON.stringify({ 2: [['09:00', '17:00']] }));
  });
});

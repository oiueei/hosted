import { render, screen, fireEvent } from '@testing-library/react';
import { describe, test, expect, vi } from 'vitest';
import ClosedDatesField from './ClosedDatesField';

// One line of comma-separated DD/MM/YYYY holidays. The page holds the raw text
// and sends it straight through, so this field's whole job is: show the value,
// report every keystroke verbatim, and surface the backend's rejection.

function renderField(over = {}) {
  const props = { id: 'edit-collection-closed-dates', value: '', onChange: vi.fn(), ...over };
  return { ...render(<ClosedDatesField {...props} />), props };
}

const field = () => screen.getByLabelText('Holidays and closures');

describe('ClosedDatesField', () => {
  test('shows the label, the format helper and an example placeholder', () => {
    renderField();
    expect(field()).toBeInTheDocument();
    expect(screen.getByText(/DD\/MM\/YYYY separated by commas/)).toBeInTheDocument();
    expect(field()).toHaveAttribute('placeholder', '25/12/2026, 26/12/2026');
  });

  test('displays the stored line', () => {
    renderField({ value: '25/12/2026, 01/01/2027' });
    expect(field()).toHaveValue('25/12/2026, 01/01/2027');
  });

  test('reports the raw text on every change — no parsing or reformatting here', () => {
    const { props } = renderField();
    fireEvent.change(field(), { target: { value: '25/12/2026,' } });
    expect(props.onChange).toHaveBeenCalledWith('25/12/2026,');
  });

  test('with no error there is no error text and the input describes only its helper', () => {
    renderField({ value: '25/12/2026' });
    expect(screen.queryByText(/more than two years away/)).toBeNull();
    expect(field().getAttribute('aria-describedby') || '').not.toMatch(/-error/);
  });

  test("the backend's reason is shown and wired to the field when error is set", () => {
    // The backend 400s e.g. a >2-years-out date rather than dropping it; the
    // owner has to be told which token and why, and a screen reader has to
    // reach that text from the field.
    renderField({
      value: '25/12/2099',
      error: "'25/12/2099' is more than two years away — check for a typo.",
    });
    const errorEl = screen.getByText(/more than two years away/);
    expect(field().getAttribute('aria-describedby')).toContain(errorEl.id);
  });
});

import { render, screen, fireEvent } from '@testing-library/react';
import { describe, test, expect, vi } from 'vitest';
import ReservationRulesFields from './ReservationRulesFields';

// These fields decide what a member can book on a reservations collection: the
// longest span, how far ahead, and which weekdays the space is open. The number
// fields are the fiddly part — HDS NumberInput is controlled, so a naive clamp
// snaps the field on every keystroke.

function renderFields(over = {}) {
  const props = {
    idPrefix: 'edit-collection',
    reservationMaxDays: 3,
    setReservationMaxDays: vi.fn(),
    reservationHorizonDays: 90,
    setReservationHorizonDays: vi.fn(),
    rentalWeekdays: [],
    setRentalWeekdays: vi.fn(),
    ...over,
  };
  return { ...render(<ReservationRulesFields {...props} />), props };
}

// HDS NumberInput wraps the numeric <input> in a role="group", so the label
// text matches twice — query the input by its spinbutton role.
const maxField = () => screen.getByRole('spinbutton', { name: 'Longest reservation (days)' });
const horizonField = () =>
  screen.getByRole('spinbutton', { name: 'How far ahead members can book (days)' });

describe('ReservationRulesFields — the bounded day fields', () => {
  test('show the stored values', () => {
    renderFields({ reservationMaxDays: 5, reservationHorizonDays: 120 });
    expect(maxField()).toHaveValue(5);
    expect(horizonField()).toHaveValue(120);
  });

  test('the field can be emptied mid-edit without snapping back to the minimum', () => {
    // The bug: value bound straight to Math.max(1, Number('')) === 1, so the
    // field jumped to 1 the moment you cleared it to retype.
    renderFields();
    fireEvent.change(maxField(), { target: { value: '' } });
    expect(maxField()).toHaveValue(null); // genuinely empty, not 1
  });

  test('an in-range value is committed to the parent on blur', () => {
    const { props } = renderFields({ reservationMaxDays: 3 });
    fireEvent.change(maxField(), { target: { value: '5' } });
    expect(props.setReservationMaxDays).not.toHaveBeenCalled(); // not yet — still typing
    fireEvent.blur(maxField());
    expect(props.setReservationMaxDays).toHaveBeenCalledWith(5);
  });

  test('a value above the ceiling is clamped to it on blur, and the field shows the clamp', () => {
    const { props } = renderFields();
    fireEvent.change(maxField(), { target: { value: '99' } });
    fireEvent.blur(maxField());
    expect(props.setReservationMaxDays).toHaveBeenCalledWith(7);
    expect(maxField()).toHaveValue(7);
  });

  test('clearing the field commits the default on blur, not an empty payload', () => {
    const { props } = renderFields({ reservationHorizonDays: 200 });
    fireEvent.change(horizonField(), { target: { value: '' } });
    fireEvent.blur(horizonField());
    expect(props.setReservationHorizonDays).toHaveBeenCalledWith(90);
    expect(horizonField()).toHaveValue(90);
  });

  test('the horizon field clamps to 365 on blur', () => {
    const { props } = renderFields();
    fireEvent.change(horizonField(), { target: { value: '400' } });
    fireEvent.blur(horizonField());
    expect(props.setReservationHorizonDays).toHaveBeenCalledWith(365);
  });

  test('a value equal to what the parent already holds is not re-emitted on blur', () => {
    const { props } = renderFields({ reservationMaxDays: 3 });
    fireEvent.blur(maxField());
    expect(props.setReservationMaxDays).not.toHaveBeenCalled();
  });

  test('a value that changed from outside the component re-syncs the field', () => {
    const { rerender, props } = renderFields({ reservationMaxDays: 3 });
    expect(maxField()).toHaveValue(3);
    rerender(<ReservationRulesFields {...props} reservationMaxDays={6} />);
    expect(maxField()).toHaveValue(6);
  });
});

describe('ReservationRulesFields — the weekday row', () => {
  test('renders the shared chips, relabelled for reservations', () => {
    renderFields();
    expect(screen.getByRole('group', { name: 'Days open for reservations' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Monday' })).toBeInTheDocument();
  });

  test('selecting a day stores its Python weekday number', () => {
    const { props } = renderFields();
    fireEvent.click(screen.getByRole('button', { name: 'Wednesday' }));
    expect(props.setRentalWeekdays).toHaveBeenCalledWith([2]);
  });
});

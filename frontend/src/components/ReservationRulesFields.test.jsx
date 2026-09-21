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
    reservationUnit: 'DAY',
    setReservationUnit: vi.fn(),
    reservationMaxDays: 3,
    setReservationMaxDays: vi.fn(),
    reservationHorizonDays: 90,
    setReservationHorizonDays: vi.fn(),
    reservationMaxActivePerMember: 10,
    setReservationMaxActivePerMember: vi.fn(),
    reservationMinMinutes: 60,
    setReservationMinMinutes: vi.fn(),
    reservationMaxMinutes: 180,
    setReservationMaxMinutes: vi.fn(),
    openingHours: {},
    setOpeningHours: vi.fn(),
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
const maxActiveField = () =>
  screen.getByRole('spinbutton', { name: 'Maximum active reservations per member' });

describe('ReservationRulesFields — the bounded day fields', () => {
  test('show the stored values', () => {
    renderFields({ reservationMaxDays: 5, reservationHorizonDays: 120 });
    expect(maxField()).toHaveValue(5);
    expect(horizonField()).toHaveValue(120);
  });

  test('the field can be emptied mid-edit without snapping back to the minimum', () => {
    // The bug: value bound straight to Math.max(1, Number('')) === 1, so the
    // field jumped to 1 the moment you cleared it to retype.
    const { props } = renderFields();
    fireEvent.change(maxField(), { target: { value: '' } });
    expect(maxField()).toHaveValue(null); // genuinely empty, not 1
    // ...and an empty field is not an answer, so the parent hears nothing.
    expect(props.setReservationMaxDays).not.toHaveBeenCalled();
  });

  test('a whole number is committed to the parent as soon as it is typed — no blur needed', () => {
    // The bug (CA, 2026-09-21): the parent only heard a number when the field
    // lost focus, so a save that came without one (the +/- stepper, a keyboard
    // Save) sent the loaded value while the screen showed the new one. Note the
    // absence of any `fireEvent.blur` below: that is the whole point.
    const { props } = renderFields({ reservationMaxDays: 3 });
    fireEvent.change(maxField(), { target: { value: '5' } });
    expect(props.setReservationMaxDays).toHaveBeenCalledWith(5);
    expect(maxField()).toHaveValue(5);
  });

  test.each([
    ['the horizon', horizonField, 'setReservationHorizonDays', 90, 91],
    ['the active-reservations cap', maxActiveField, 'setReservationMaxActivePerMember', 10, 11],
  ])(
    'the + stepper on %s reaches the parent with no focus change at all',
    (_n, field, setter, from, to) => {
      // The buttons beside the number are what the owner actually presses (CA's
      // screenshot, 2026-09-21). They take focus themselves and never touch the
      // input, so its blur never fires: whatever they change has to reach the
      // parent on its own, or a Save afterwards sends the loaded value.
      const { props } = renderFields();
      const stepUp = field().closest('[role="group"]').querySelectorAll('button')[1];
      expect(field()).toHaveValue(from);

      fireEvent.click(stepUp);

      expect(props[setter]).toHaveBeenCalledWith(to);
      expect(field()).toHaveValue(to);
    }
  );

  test('a value above the ceiling is clamped to it at once, and the field shows the clamp', () => {
    // What the field shows is what the page will save: an out-of-range number
    // does not sit on screen as something a later save would silently replace.
    const { props } = renderFields();
    fireEvent.change(maxField(), { target: { value: '99' } });
    expect(props.setReservationMaxDays).toHaveBeenCalledWith(7);
    expect(maxField()).toHaveValue(7);
  });

  test('a half-typed value is a draft — not committed, and settled by blur', () => {
    // Not an answer yet: nothing goes to the parent while the field holds a
    // decimal, and blur rounds it the way it always did.
    const { props } = renderFields({ reservationMaxDays: 3 });
    fireEvent.change(maxField(), { target: { value: '4.5' } });
    expect(props.setReservationMaxDays).not.toHaveBeenCalled();
    fireEvent.blur(maxField());
    expect(props.setReservationMaxDays).toHaveBeenCalledWith(5);
  });

  test('clearing the field commits the default on blur, not an empty payload', () => {
    const { props } = renderFields({ reservationHorizonDays: 200 });
    fireEvent.change(horizonField(), { target: { value: '' } });
    fireEvent.blur(horizonField());
    expect(props.setReservationHorizonDays).toHaveBeenCalledWith(90);
    expect(horizonField()).toHaveValue(90);
  });

  test('the horizon field takes a typed number at once, and clamps to 365', () => {
    // The field this was reported on ("how far ahead can they book"): a typed
    // 30 reaches the page without the field ever losing focus.
    const { props } = renderFields();
    fireEvent.change(horizonField(), { target: { value: '30' } });
    expect(props.setReservationHorizonDays).toHaveBeenLastCalledWith(30);

    fireEvent.change(horizonField(), { target: { value: '400' } });
    expect(props.setReservationHorizonDays).toHaveBeenLastCalledWith(365);
    expect(horizonField()).toHaveValue(365);
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

  test('the active-reservations cap shows the stored value and clamps to 1..50 on blur', () => {
    const { props } = renderFields({ reservationMaxActivePerMember: 25 });
    expect(maxActiveField()).toHaveValue(25);

    fireEvent.change(maxActiveField(), { target: { value: '99' } });
    fireEvent.blur(maxActiveField());
    expect(props.setReservationMaxActivePerMember).toHaveBeenCalledWith(50);

    fireEvent.change(maxActiveField(), { target: { value: '' } });
    fireEvent.blur(maxActiveField());
    expect(props.setReservationMaxActivePerMember).toHaveBeenCalledWith(10); // fallback
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

// The trap this whole group exists to catch: HDS SelectionGroup does not
// flatten a nested array of children, so a naive `.map()` renders a fieldset
// with a legend and ZERO radios — no error anywhere (frontend/CLAUDE.md). A
// bare radio-count assertion is what makes that failure loud instead of silent.
describe('ReservationRulesFields — the DAY/HOUR unit selector', () => {
  test('renders exactly two radios', () => {
    renderFields();
    expect(screen.getAllByRole('radio')).toHaveLength(2);
  });

  test('DAY is checked by default', () => {
    renderFields();
    expect(screen.getByRole('radio', { name: 'By day' })).toBeChecked();
    expect(screen.getByRole('radio', { name: 'By hour' })).not.toBeChecked();
  });

  test('an explicit HOUR value checks the other radio', () => {
    renderFields({ reservationUnit: 'HOUR' });
    expect(screen.getByRole('radio', { name: 'By hour' })).toBeChecked();
  });

  test('selecting "By hour" notifies the parent', () => {
    const { props } = renderFields();
    fireEvent.click(screen.getByRole('radio', { name: 'By hour' }));
    expect(props.setReservationUnit).toHaveBeenCalledWith('HOUR');
  });
});

describe('ReservationRulesFields — DAY vs HOUR field visibility', () => {
  test('DAY mode shows the day fields, not the hour ones', () => {
    renderFields();
    expect(maxField()).toBeInTheDocument();
    expect(screen.getByRole('group', { name: 'Days open for reservations' })).toBeInTheDocument();
    expect(
      screen.queryByRole('spinbutton', { name: 'Shortest reservation (minutes)' })
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('spinbutton', { name: 'Longest reservation (minutes)' })
    ).not.toBeInTheDocument();
    expect(screen.queryByText('Weekly opening hours')).not.toBeInTheDocument();
  });

  test('HOUR mode shows the minute fields, not the day ones', () => {
    renderFields({
      reservationUnit: 'HOUR',
      reservationMinMinutes: 60,
      reservationMaxMinutes: 180,
      openingHours: {},
    });
    expect(
      screen.getByRole('spinbutton', { name: 'Shortest reservation (minutes)' })
    ).toBeInTheDocument();
    expect(
      screen.getByRole('spinbutton', { name: 'Longest reservation (minutes)' })
    ).toBeInTheDocument();
    expect(screen.getByText('Weekly opening hours')).toBeInTheDocument();
    expect(screen.queryByRole('spinbutton', { name: 'Longest reservation (days)' })).toBeNull();
    expect(screen.queryByRole('group', { name: 'Days open for reservations' })).toBeNull();
  });

  test('the minimum and maximum show their own stored values', () => {
    renderFields({
      reservationUnit: 'HOUR',
      reservationMinMinutes: 15,
      reservationMaxMinutes: 100,
      openingHours: {},
    });
    expect(screen.getByRole('spinbutton', { name: 'Shortest reservation (minutes)' })).toHaveValue(
      15
    );
    expect(screen.getByRole('spinbutton', { name: 'Longest reservation (minutes)' })).toHaveValue(
      100
    );
  });

  test('the horizon and active-cap fields show in both modes', () => {
    renderFields({ reservationUnit: 'HOUR' });
    expect(horizonField()).toBeInTheDocument();
    expect(maxActiveField()).toBeInTheDocument();
  });
});

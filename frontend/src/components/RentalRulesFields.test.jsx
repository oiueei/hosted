import { render, screen, fireEvent } from '@testing-library/react';
import { describe, test, expect, vi } from 'vitest';
import RentalRulesFields from './RentalRulesFields';

// These fields decide what a renter can pick on RequestThingPage: the durations
// become the length Select, the weekdays gate the pickup DateInput. A value that
// leaves here in the wrong shape or the wrong numbering silently narrows — or
// wrongly widens — every rental in the collection.

function renderFields(over = {}) {
  const props = {
    idPrefix: 'edit-collection',
    rentalDurations: [],
    setRentalDurations: vi.fn(),
    rentalWeekdays: [],
    setRentalWeekdays: vi.fn(),
    ...over,
  };
  return { ...render(<RentalRulesFields {...props} />), props };
}

// Python weekday numbering (0=Mon … 6=Sun), which is what the backend stores.
const chip = (name) => screen.getByRole('button', { name });

describe('RentalRulesFields weekday chips', () => {
  test('renders one chip per weekday, each named in full for screen readers', () => {
    renderFields();
    const group = screen.getByRole('group', { name: /pick-?up|weekday|day/i });
    expect(group).toBeInTheDocument();
    // The chip face is a single narrow letter (L M X J V S D in Spanish), so
    // the full weekday name has to ride along as the accessible name.
    expect(screen.getByRole('button', { name: 'Monday' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Sunday' })).toBeInTheDocument();
  });

  test('selecting Monday stores 0 — Python numbering, not JS', () => {
    // JS getDay() calls Sunday 0; the backend calls Monday 0. Getting this
    // backwards shifts every allowed pickup day by one.
    const { props } = renderFields();
    fireEvent.click(chip('Monday'));
    expect(props.setRentalWeekdays).toHaveBeenCalledWith([0]);
  });

  test('selecting Sunday stores 6, the last Python weekday', () => {
    const { props } = renderFields();
    fireEvent.click(chip('Sunday'));
    expect(props.setRentalWeekdays).toHaveBeenCalledWith([6]);
  });

  test('a selected chip reports itself pressed', () => {
    renderFields({ rentalWeekdays: [0, 4] });
    expect(chip('Monday')).toHaveAttribute('aria-pressed', 'true');
    expect(chip('Friday')).toHaveAttribute('aria-pressed', 'true');
    expect(chip('Tuesday')).toHaveAttribute('aria-pressed', 'false');
  });

  test('clicking a selected chip removes just that day', () => {
    const { props } = renderFields({ rentalWeekdays: [0, 2, 4] });
    fireEvent.click(chip('Wednesday'));
    expect(props.setRentalWeekdays).toHaveBeenCalledWith([0, 4]);
  });

  test('days come back sorted however they were clicked', () => {
    // The backend compares these against a computed weekday; an unsorted list is
    // harmless there but makes the saved value churn on every edit.
    const { props } = renderFields({ rentalWeekdays: [4] });
    fireEvent.click(chip('Monday'));
    expect(props.setRentalWeekdays).toHaveBeenCalledWith([0, 4]);
  });
});

describe('RentalRulesFields durations', () => {
  test('offers the preset lengths, labelled not raw', () => {
    renderFields();
    fireEvent.click(screen.getByRole('combobox', { name: /length|duration/i }));
    expect(screen.getByRole('option', { name: '1 day' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: '1 week' })).toBeInTheDocument();
  });

  test('a stored duration shows as selected when the form loads', () => {
    // The owner must see what the collection already offers, or they will
    // re-pick it and think they changed nothing.
    renderFields({ rentalDurations: [7] });
    fireEvent.click(screen.getByRole('combobox', { name: /length|duration/i }));
    expect(screen.getByRole('option', { name: '1 week', selected: true })).toBeInTheDocument();
  });

  test('picking a length stores it as a number, not the option string', () => {
    // HDS Select hands back `{ value: '7' }`. Saving the string would make the
    // backend's day arithmetic concatenate instead of add.
    const { props } = renderFields();
    fireEvent.click(screen.getByRole('combobox', { name: /length|duration/i }));
    fireEvent.click(screen.getByRole('option', { name: '1 week' }));
    expect(props.setRentalDurations).toHaveBeenCalledWith([7]);
    expect(props.setRentalDurations.mock.calls[0][0].every((d) => typeof d === 'number')).toBe(true);
  });
});

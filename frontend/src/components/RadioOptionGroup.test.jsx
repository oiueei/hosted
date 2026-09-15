import { render, screen, fireEvent } from '@testing-library/react';
import { test, expect, vi } from 'vitest';
import RadioOptionGroup from './RadioOptionGroup';

// A bare radio-count assertion is not enough on its own here — see the
// component's own docstring for why a duplicate-id regression passes it
// while every radio's accessible name goes silently blank. Every test below
// that checks a radio "by name" is what actually proves the wiring works.

const OPTIONS = [
  { value: '1', label: '1 hour' },
  { value: '2', label: '2 hours' },
  { value: 'fullDay', label: 'Full day' },
];

function renderGroup(over = {}) {
  const onChange = vi.fn();
  const utils = render(
    <RadioOptionGroup
      idPrefix="reservation-duration"
      name="reservation-duration"
      label="How long?"
      options={OPTIONS}
      value=""
      onChange={onChange}
      {...over}
    />
  );
  return { ...utils, onChange };
}

test('renders exactly one radio per option', () => {
  renderGroup();
  expect(screen.getAllByRole('radio')).toHaveLength(3);
});

test('each radio is reachable by its own label as an accessible name', () => {
  renderGroup();
  expect(screen.getByRole('radio', { name: '1 hour' })).toBeInTheDocument();
  expect(screen.getByRole('radio', { name: '2 hours' })).toBeInTheDocument();
  expect(screen.getByRole('radio', { name: 'Full day' })).toBeInTheDocument();
});

test('the group itself is named by its label', () => {
  renderGroup();
  expect(screen.getByRole('group', { name: 'How long?' })).toBeInTheDocument();
});

test('the stored value checks the matching radio, and only that one', () => {
  renderGroup({ value: '2' });
  expect(screen.getByRole('radio', { name: '2 hours' })).toBeChecked();
  expect(screen.getByRole('radio', { name: '1 hour' })).not.toBeChecked();
  expect(screen.getByRole('radio', { name: 'Full day' })).not.toBeChecked();
});

test('selecting an option notifies the parent with its value', () => {
  const { onChange } = renderGroup();
  fireEvent.click(screen.getByRole('radio', { name: 'Full day' }));
  expect(onChange).toHaveBeenCalledWith('fullDay');
});

test('a changed option list re-renders with the new radios', () => {
  const { rerender } = renderGroup({ options: [{ value: '1', label: '1 hour' }] });
  expect(screen.getAllByRole('radio')).toHaveLength(1);
  rerender(
    <RadioOptionGroup
      idPrefix="reservation-duration"
      name="reservation-duration"
      label="How long?"
      options={OPTIONS}
      value=""
      onChange={vi.fn()}
    />
  );
  expect(screen.getAllByRole('radio')).toHaveLength(3);
});

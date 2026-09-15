import { render, screen, fireEvent, within } from '@testing-library/react';
import { describe, test, expect, vi } from 'vitest';
import OpeningHoursEditor from './OpeningHoursEditor';

// The weekly opening-hours grid a HOUR-unit reservations collection's owner
// edits. Unvalidated by design (like ClosedDatesField) — the backend is the
// one source of truth for start<end, overlap and the block-count cap.

function renderEditor(over = {}) {
  const onChange = vi.fn();
  const utils = render(
    <OpeningHoursEditor idPrefix="edit-collection" value={{}} onChange={onChange} {...over} />
  );
  return { ...utils, onChange };
}

describe('OpeningHoursEditor — one row per weekday', () => {
  test('renders all seven weekdays as named groups', () => {
    renderEditor();
    for (const day of [
      'Monday',
      'Tuesday',
      'Wednesday',
      'Thursday',
      'Friday',
      'Saturday',
      'Sunday',
    ]) {
      expect(screen.getByRole('group', { name: day })).toBeInTheDocument();
    }
  });

  test('a day with no blocks shows as closed', () => {
    renderEditor({ value: {} });
    const monday = screen.getByRole('group', { name: 'Monday' });
    expect(within(monday).getByText('Closed')).toBeInTheDocument();
  });

  test('a day with a block shows its time range, not "Closed"', () => {
    renderEditor({ value: { 0: [['10:00', '14:00']] } });
    const monday = screen.getByRole('group', { name: 'Monday' });
    expect(within(monday).queryByText('Closed')).toBeNull();
    expect(within(monday).getAllByLabelText('Hours')).toHaveLength(2); // start + end
  });
});

describe('OpeningHoursEditor — adding and removing blocks', () => {
  test('adding a block on a closed day sends an empty range', () => {
    const { onChange } = renderEditor({ value: {} });
    const monday = screen.getByRole('group', { name: 'Monday' });
    fireEvent.click(within(monday).getByRole('button', { name: 'Add a time range' }));
    expect(onChange).toHaveBeenCalledWith({ 0: [['', '']] });
  });

  test('adding a second block keeps the first untouched', () => {
    const { onChange } = renderEditor({ value: { 0: [['10:00', '14:00']] } });
    const monday = screen.getByRole('group', { name: 'Monday' });
    fireEvent.click(within(monday).getByRole('button', { name: 'Add a time range' }));
    expect(onChange).toHaveBeenCalledWith({
      0: [
        ['10:00', '14:00'],
        ['', ''],
      ],
    });
  });

  test('removing the only block clears the day back to closed', () => {
    const { onChange } = renderEditor({ value: { 0: [['10:00', '14:00']] } });
    const monday = screen.getByRole('group', { name: 'Monday' });
    fireEvent.click(within(monday).getByRole('button', { name: 'Remove' }));
    expect(onChange).toHaveBeenCalledWith({});
  });

  test('removing one of two blocks keeps the other', () => {
    const { onChange } = renderEditor({
      value: {
        0: [
          ['10:00', '14:00'],
          ['16:00', '20:00'],
        ],
      },
    });
    const monday = screen.getByRole('group', { name: 'Monday' });
    fireEvent.click(within(monday).getAllByRole('button', { name: 'Remove' })[0]);
    expect(onChange).toHaveBeenCalledWith({ 0: [['16:00', '20:00']] });
  });

  test('a day caps at 4 blocks — no "Add" button past the cap', () => {
    renderEditor({
      value: {
        0: [
          ['00:00', '01:00'],
          ['02:00', '03:00'],
          ['04:00', '05:00'],
          ['06:00', '07:00'],
        ],
      },
    });
    const monday = screen.getByRole('group', { name: 'Monday' });
    expect(within(monday).queryByRole('button', { name: 'Add a time range' })).toBeNull();
  });

  test('typing a start time updates only that side of that block', () => {
    const { onChange, container } = renderEditor({ value: { 0: [['10:00', '14:00']] } });
    const startId = 'edit-collection-oh-0-0-start';
    fireEvent.change(container.querySelector(`#${startId}-hours`), { target: { value: '09' } });
    fireEvent.change(container.querySelector(`#${startId}-minutes`), { target: { value: '30' } });
    expect(onChange).toHaveBeenLastCalledWith({ 0: [['09:30', '14:00']] });
  });

  test('other weekdays are untouched by an edit on one', () => {
    const { onChange } = renderEditor({ value: { 4: [['10:00', '14:00']] } }); // Friday
    const monday = screen.getByRole('group', { name: 'Monday' });
    fireEvent.click(within(monday).getByRole('button', { name: 'Add a time range' }));
    expect(onChange).toHaveBeenCalledWith({
      4: [['10:00', '14:00']],
      0: [['', '']],
    });
  });
});

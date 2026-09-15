import { render, screen } from '@testing-library/react';
import { describe, test, expect } from 'vitest';
import OwnerBookingsList from './OwnerBookingsList';

const wholeDayBooking = {
  code: 'BKG001',
  status: 'ACCEPTED',
  start_date: '2026-10-05',
  end_date: '2026-10-06',
};

const hourlyBooking = {
  code: 'BKG002',
  status: 'ACCEPTED',
  start_date: '2026-10-05',
  end_date: '2026-10-06',
  start_time: '11:00:00',
  end_time: '13:00:00',
};

describe('OwnerBookingsList', () => {
  test('renders nothing for a non-owner', () => {
    const { container } = render(
      <OwnerBookingsList bookings={[wholeDayBooking]} activePendingCode={null} isOwner={false} />
    );
    expect(container).toBeEmptyDOMElement();
  });

  test('a whole-day booking shows a date range', () => {
    render(
      <OwnerBookingsList bookings={[wholeDayBooking]} activePendingCode={null} isOwner={true} />
    );
    expect(screen.getByText(/05\/10\/2026 — 06\/10\/2026/)).toBeInTheDocument();
  });

  test('an HOUR-unit reservation shows the date once and both times, not the day-based end_date', () => {
    render(
      <OwnerBookingsList bookings={[hourlyBooking]} activePendingCode={null} isOwner={true} />
    );
    expect(screen.getByText(/05\/10\/2026, 11:00–13:00/)).toBeInTheDocument();
    expect(screen.queryByText(/06\/10\/2026/)).toBeNull();
  });
});

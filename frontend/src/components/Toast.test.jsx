import { render, screen, act, fireEvent } from '@testing-library/react';
import { describe, test, expect, vi, beforeEach, afterEach } from 'vitest';
import Toast from './Toast';

// An error toast says why something did not happen; it must stay until the reader
// closes it (WCAG 2.2.1). A success only confirms what the page already shows, so
// it may go by itself. Timers are faked so the six seconds pass at once.

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

const WAIT_PAST_AUTO_CLOSE = 20000;

describe('Toast', () => {
  test('an error stays on screen long after the auto-close delay', () => {
    const onClose = vi.fn();
    render(<Toast toast={{ type: 'error', message: 'The dates overlap.' }} onClose={onClose} />);

    act(() => vi.advanceTimersByTime(WAIT_PAST_AUTO_CLOSE));

    expect(screen.getByText('The dates overlap.')).toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();
  });

  test('an error still closes when its close button is pressed', () => {
    const onClose = vi.fn();
    render(<Toast toast={{ type: 'error', message: 'The dates overlap.' }} onClose={onClose} />);

    fireEvent.click(screen.getByRole('button', { name: 'Close' }));
    act(() => vi.advanceTimersByTime(WAIT_PAST_AUTO_CLOSE));

    expect(onClose).toHaveBeenCalled();
  });

  test('a success closes by itself', () => {
    const onClose = vi.fn();
    render(<Toast toast={{ type: 'success', message: 'Saved.' }} onClose={onClose} />);
    expect(onClose).not.toHaveBeenCalled();

    act(() => vi.advanceTimersByTime(WAIT_PAST_AUTO_CLOSE));

    expect(onClose).toHaveBeenCalled();
  });

  test('a message key is translated where the toast is painted', () => {
    render(<Toast toast={{ type: 'error', messageKey: 'common.connectionError' }} />);

    expect(screen.getByText('Connection error.')).toBeInTheDocument();
  });
});

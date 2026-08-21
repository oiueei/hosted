import { render, screen } from '@testing-library/react';
import { describe, test, expect } from 'vitest';
import ThingInfoRows from './ThingInfoRows';

// The row that only the deposit exists to protect (DEPOSIT_PLAN.md §10, S6):
// a RENT thing with a price AND a deposit must not read as one number.

describe('ThingInfoRows — deposit row', () => {
  test('never appears on a thing that carries no deposit', () => {
    render(<ThingInfoRows thing={{ type: 'GIFT_THING', fee: null }} isDateBased={false} />);
    expect(screen.queryByText(/deposit/i)).toBeNull();
  });

  test('shows the deposit amount, marked as returnable — not the price wording', () => {
    render(<ThingInfoRows thing={{ type: 'LEND_THING', deposit: '50.00' }} isDateBased={false} />);

    expect(screen.getByText('Deposit.')).toBeInTheDocument();
    expect(screen.getByText(/50\.00 €/)).toBeInTheDocument();
    expect(screen.getByText(/refundable/i)).toBeInTheDocument();
  });

  test('a RENT thing shows both rows, under two different labels', () => {
    render(
      <ThingInfoRows thing={{ type: 'RENT_THING', fee: '10.00', deposit: '50.00' }} isDateBased />
    );

    // "Price." and "Deposit." both present — the reader is never left to guess
    // whether 10 and 50 are one number or two separate promises.
    expect(screen.getByText('Price.')).toBeInTheDocument();
    expect(screen.getByText('Deposit.')).toBeInTheDocument();
    expect(screen.getByText(/10\.00 €/)).toBeInTheDocument();
    expect(screen.getByText(/50\.00 €/)).toBeInTheDocument();
  });
});

import { render, screen } from '@testing-library/react';
import { describe, test, expect } from 'vitest';
import DepositPolicy from './DepositPolicy';
import ThingInfoRows from './ThingInfoRows';

/**
 * How deposits work is shown under the deposit of a thing that has one — the group's
 * words, or a network's pickup point's, resolved by the server into `deposit_policy`.
 */
const THING = { type: 'LEND_THING', deposit: '50.00', deposit_policy: '50 €, back in one piece' };

describe('DepositPolicy', () => {
  test('a thing with a deposit shows the policy', () => {
    render(<DepositPolicy thing={THING} />);

    expect(screen.getByTestId('deposit-policy')).toHaveTextContent('50 €, back in one piece');
  });

  test('a thing with no deposit shows none, however the group wrote it', () => {
    render(<DepositPolicy thing={{ ...THING, deposit: null }} />);
    render(<DepositPolicy thing={{ ...THING, deposit: '0.00' }} />);

    expect(screen.queryByTestId('deposit-policy')).toBeNull();
  });

  test('a group with no policy shows nothing under the deposit', () => {
    render(<DepositPolicy thing={{ ...THING, deposit_policy: '' }} />);

    expect(screen.queryByTestId('deposit-policy')).toBeNull();
  });

  test('one text per language: the reader’s own', () => {
    const policy = '{"es": "50 €, se devuelven", "en": "50 €, refunded"}';
    render(<DepositPolicy thing={{ ...THING, deposit_policy: policy }} />);

    expect(screen.getByTestId('deposit-policy')).toHaveTextContent(
      /^50 €, (refunded|se devuelven)$/
    );
    expect(screen.getByTestId('deposit-policy').textContent).not.toContain('{');
  });

  test('markup in the owner’s words stays text', () => {
    render(<DepositPolicy thing={{ ...THING, deposit_policy: '<b>x</b>' }} />);

    expect(screen.getByTestId('deposit-policy')).toHaveTextContent('<b>x</b>');
    expect(document.querySelector('[data-testid="deposit-policy"] b')).toBeNull();
  });

  test('the thing’s rows carry it under the deposit', () => {
    render(<ThingInfoRows thing={{ ...THING, fee: null }} isDateBased />);

    expect(screen.getByText('50.00 € (refundable)')).toBeInTheDocument();
    expect(screen.getByTestId('deposit-policy')).toBeInTheDocument();
  });

  test('and no policy without a deposit', () => {
    render(<ThingInfoRows thing={{ ...THING, deposit: null, fee: null }} isDateBased />);

    expect(screen.queryByTestId('deposit-policy')).toBeNull();
  });
});

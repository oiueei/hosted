import { describe, test, expect } from 'vitest';
import { declarations } from './cssRules';

/**
 * The label of every button — HDS `Button` and `ButtonLink`, which both carry
 * `hds-button` — is 16/24 Bold. HDS sets its own size and weight, so the rule is
 * `!important`; jsdom paints nothing, so what is pinned is what it declares.
 */
describe('the label of a button', () => {
  test('is 16px, bold, on a 24px line', () => {
    expect(declarations('.hds-button', 'font-size')).toEqual(['var(--fontsize-body-m) !important']);
    expect(declarations('.hds-button', 'font-weight')).toEqual(['700 !important']);
    expect(declarations('.hds-button', 'line-height')).toEqual(['24px !important']);
  });
});

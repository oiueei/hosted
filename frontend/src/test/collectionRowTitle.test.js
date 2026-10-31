import { describe, it, expect } from 'vitest';
import { rulesFor } from './cssRules';

const SELECTOR = ".collections-grid *[class*='Linkbox-module_heading']";

describe('the title of a collection row', () => {
  const [rule, ...others] = rulesFor(SELECTOR);

  it('is declared by exactly one rule', () => {
    expect(rule).toBeTruthy();
    expect(others).toHaveLength(0);
  });

  it('takes the size of HDS heading-s and a weight of 700', () => {
    expect(rule).toMatch(/font-size:\s*var\(--fontsize-heading-s\)/);
    expect(rule).toMatch(/font-weight:\s*700/);
  });

  it('leaves the line height and the letter spacing to HDS', () => {
    expect(rule).not.toMatch(/line-height/);
    expect(rule).not.toMatch(/letter-spacing/);
  });
});

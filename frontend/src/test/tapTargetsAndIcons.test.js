import { describe, test, expect } from 'vitest';
import { declarations } from './cssRules';

/**
 * DESIGN §4: every touch target is at least 44×44px. DESIGN §11: an icon is black,
 * `--color-black-40` only when disabled.
 *
 * jsdom does no layout, so this pins what the stylesheet declares for the controls
 * that fell short: the entries of the two corner menus (their padding alone made
 * them about 40px tall), the text-styled button of the share door ("Use another
 * email instead", which had no padding at all) and the (i) of `InfoPopover`, which
 * was grey while enabled.
 */
describe('tap targets', () => {
  test.each([
    '.account-menu-panel a',
    '.collection-menu-panel a',
    '.collection-menu-panel button',
    '.digest-pref-button',
  ])('%s is at least 44px tall', (selector) => {
    expect(declarations(selector, 'min-height')).toContain('44px');
  });

  // The menu entries' padding sits inside the 44px, not on top of it.
  test.each(['.account-menu-panel a', '.collection-menu-panel a', '.collection-menu-panel button'])(
    '%s counts its padding inside its height',
    (selector) => {
      expect(declarations(selector, 'box-sizing')).toContain('border-box');
    }
  );
});

describe('icons are black', () => {
  test('the (i) of an info popover is black-90 while enabled, with no other colour declared', () => {
    expect(declarations('.info-popover-button', 'color')).toEqual(['var(--color-black-90)']);
    expect(declarations('.info-popover-button:hover', 'color')).toEqual([]);
  });
});

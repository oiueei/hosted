import { describe, test, expect } from 'vitest';
import { declarations, declarationsInMedia, rulesFor } from './cssRules';

/**
 * A loose action button goes in a `.button-row-wide`, even when it is the only one
 * (CA, 2026-10-04): under 768px the row stacks its children and takes each across
 * the width of the screen, and on a desktop it leaves them at the width of their
 * own text. The pages pin that their buttons sit in one; this pins what the row
 * does, since jsdom applies no CSS.
 */
describe('.button-row-wide', () => {
  const MOBILE = '(max-width: 767px)';

  test('under 768px its links and buttons are as wide as the row', () => {
    for (const child of [
      '.button-row-wide > a',
      '.button-row-wide > a button',
      '.button-row-wide > button',
    ]) {
      expect(declarationsInMedia(MOBILE, child, 'width'), child).toEqual(['100%']);
    }
  });

  test('under 768px the row stacks them', () => {
    expect(declarationsInMedia(MOBILE, '.button-row-wide', 'flex-direction')).toEqual(['column']);
  });

  test('outside the media query nothing makes them wide: on a desktop they keep their own width', () => {
    // The row itself is a flex container; what must not exist outside the
    // media query is a `width` on its children.
    expect(rulesFor('.button-row-wide').some((body) => /display:\s*flex/.test(body))).toBe(true);
    const everywhere = declarations('.button-row-wide > a', 'width');
    const underMobile = declarationsInMedia(MOBILE, '.button-row-wide > a', 'width');
    expect(everywhere).toEqual(underMobile);
  });
});

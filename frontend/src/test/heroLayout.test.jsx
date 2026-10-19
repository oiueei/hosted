import { describe, test, expect } from 'vitest';
import {
  css,
  declarations,
  declarationsInMedia,
  declared,
  rulesFor,
  rulesIn,
  mediaBlocks,
} from './cssRules';

/**
 * The measures every hero is drawn to: the page's side margin (16px under 768px,
 * 24px from it), an 80px navigation band, one vertical rhythm of that margin between
 * the blocks, 24px above the koro and a 48px koro. jsdom paints nothing, so these pin
 * what the stylesheet declares and where, in the manner of `heroCornerLayout.test.jsx`.
 */
const WIDE = '(min-width: 768px)';

describe('the page margin', () => {
  test('is 16px below 768px and 24px from it, on :root', () => {
    expect(declarations(':root', '--page-margin')).toEqual([
      'var(--spacing-s)',
      'var(--spacing-m)',
    ]);
    expect(declarationsInMedia(WIDE, ':root', '--page-margin')).toEqual(['var(--spacing-m)']);
  });

  test('the content column and the hero column both take it on their sides', () => {
    expect(declarations('.page-container', 'padding')).toEqual(['var(--page-margin)']);
    const [heroPadding] = declarations('.form-hero-content', 'padding');
    expect(heroPadding.split(/\s+/)[1]).toBe('var(--page-margin)');
  });

  test('the corner row keeps the margin from the content column’s right edge', () => {
    const [corner] = declarations('.hero-corners', 'right');
    expect(corner).toMatch(/\+ var\(--page-margin\)\)$/);
  });
});

describe('the hero’s navigation band', () => {
  test('is 80px, as the top padding, and 24px close the content against the koro', () => {
    const rule = rulesFor('.form-hero-content').find((body) => declared(body, '--hero-band'));
    expect(declared(rule, '--hero-band')).toBe('80px');
    const [padding] = declarations('.form-hero-content', 'padding');
    expect(padding.split(/\s+/)).toEqual([
      'var(--hero-band)',
      'var(--page-margin)',
      'var(--spacing-m)',
    ]);
  });

  test('the icon row is centred in it: 44px icons from y=18', () => {
    expect(declarations('.hero-corners', 'top')).toEqual(['18px']);
  });

  test('the back link’s 24px line sits at y=28 of it and gives the rest of the band back', () => {
    const sel = '.form-hero-content .back-link';
    expect(declarations(sel, 'line-height')).toEqual(['24px']);
    // A flex row centring the arrow with the text, 24px tall: an inline svg on the
    // baseline made it 31px and the band closed at y=87.
    expect(declarations(sel, 'display')).toEqual(['flex']);
    expect(declarations(sel, 'align-items')).toEqual(['center']);
    expect(declarations(sel, 'min-height')).toEqual(['24px']);
    // 28px - 80px climbs back into the padding; 28px under it closes 28 + 24 + 28 = 80.
    expect(declarations(sel, 'margin')).toEqual(['calc(28px - var(--hero-band)) 0 28px']);
  });
});

describe('the hero’s title', () => {
  test('is 40px under 768px and 48px from it, bold, tight, with no padding of its own', () => {
    expect(declarations('.form-hero-title', 'font-size')).toEqual([
      'var(--fontsize-heading-xl-mobile)',
      'var(--fontsize-heading-xl)',
    ]);
    expect(declarationsInMedia(WIDE, '.form-hero-title', 'font-size')).toEqual([
      'var(--fontsize-heading-xl)',
    ]);
    expect(declarations('.form-hero-title', 'letter-spacing')).toEqual(['-0.8px', '-1px']);
    expect(declarationsInMedia(WIDE, '.form-hero-title', 'letter-spacing')).toEqual(['-1px']);
    expect(declarations('.form-hero-title', 'font-weight')).toEqual(['700']);
    expect(declarations('.form-hero-title', 'line-height')).toEqual(['var(--lineheight-s)']);
    expect(declarations('.form-hero-title', 'padding')).toEqual([]);
  });
});

describe('the hero’s text', () => {
  test('is 18/28 Medium and carries no padding', () => {
    expect(declarations('.form-hero-text', 'font-size')).toEqual(['var(--fontsize-body-l)']);
    expect(declarations('.form-hero-text', 'line-height')).toEqual(['28px']);
    expect(declarations('.form-hero-text', 'font-weight')).toEqual(['500']);
    expect(declarations('.form-hero-text', 'padding-bottom')).toEqual([]);
    expect(declarations('.form-hero-text', 'padding')).toEqual([]);
  });

  test('every block after the first one is one margin under the one before', () => {
    const rhythm = '.form-hero-content > :not(.hero-corners):not(.back-link) ~ *';
    expect(declarations(rhythm, 'margin-top')).toEqual(['var(--page-margin)']);
    // A live region with nothing in it adds none.
    expect(declarations('.form-hero-content > .status-region:empty', 'margin-top')).toEqual(['0']);
    // And the rule that used to space the buttons of a hero apart is gone.
    expect(declarations('.hero-actions', 'margin-top')).toEqual([]);
  });
});

describe('the hero’s buttons', () => {
  test('are 24px apart', () => {
    expect(declarations('.form-hero .button-row-wide', 'gap')).toEqual(['var(--spacing-m)']);
  });

  test('outside a hero the row keeps its own gap', () => {
    expect(declarations('.button-row-wide', 'gap')).toEqual(['var(--spacing-s)']);
  });
});

describe('the hero’s koro', () => {
  test('is 48px tall', () => {
    expect(declarations('.form-hero-koros svg', 'height')).toEqual(['48px']);
  });
});

describe('the footer’s column', () => {
  test('takes the same side margin', () => {
    const [padding] = declarations('.site-footer-inner', 'padding');
    expect(padding.split(/\s+/)[1]).toBe('var(--page-margin)');
  });
});

test('nothing else in the stylesheet still hard-codes 16px as the page margin', () => {
  // The two columns used to say `var(--spacing-s)` on their own; a block that
  // went back to it would be 16px at 768px and the page 24.
  const columns = [
    ...rulesFor('.page-container'),
    ...rulesFor('.form-hero-content'),
    ...rulesFor('.site-footer-inner'),
  ];
  for (const body of columns) expect(body).not.toMatch(/padding:[^;]*var\(--spacing-s\)/);
  expect(mediaBlocks(WIDE).length).toBeGreaterThan(0);
  expect(rulesIn(css, ':root').length).toBeGreaterThan(0);
});

import { describe, test, expect } from 'vitest';
import { declarations } from './cssRules';

/**
 * The grid of cards and the card, to the measures the collection page is drawn to.
 * jsdom paints nothing, so what is pinned is what the stylesheet declares. A card's
 * attribute rows share their classes with a thing's page, which reads them at the
 * larger size: the card's values are on `.thing-card …` rules, and the page's stay.
 */
describe('the grid of cards', () => {
  test('takes its columns from the HDS breakpoints and is one page margin apart', () => {
    expect(declarations('.things-grid', 'grid-template-columns')).toEqual([
      'repeat(var(--grid-columns), 1fr)',
    ]);
    expect(declarations('.things-grid', 'gap')).toEqual(['var(--page-margin)']);
  });
});

describe('the card', () => {
  test('has no radius, a white ground, 16px above and at the sides and 24px under', () => {
    expect(declarations('.thing-card', 'border-radius')).toEqual(['0']);
    expect(declarations('.thing-card', 'background')).toEqual(['var(--color-white)']);
    expect(declarations('.thing-card', 'padding')).toEqual([
      'var(--spacing-s) var(--spacing-s) var(--spacing-m)',
    ]);
  });

  test('its image, text, attributes and buttons are 16px apart', () => {
    expect(declarations('.thing-card', 'gap')).toEqual(['var(--spacing-s)']);
    expect(declarations('.thing-card-body', 'gap')).toEqual(['var(--spacing-s)']);
    expect(declarations('.thing-card-buttons', 'gap')).toEqual(['var(--spacing-s)']);
    // The gap is the whole of the space above the buttons: no padding adds to it.
    expect(declarations('.thing-card-buttons', 'padding-top')).toEqual([]);
  });

  test('the image fills the inside, 3:2, with no radius — and so does a carousel’s', () => {
    expect(declarations('.thing-card-image', 'width')).toEqual(['100%']);
    expect(declarations('.thing-card-image', 'aspect-ratio')).toEqual(['3 / 2']);
    expect(declarations('.thing-card-image', 'border-radius')).toEqual(['0']);
    expect(declarations('.image-carousel-viewport--card', 'width')).toEqual(['100%']);
    expect(declarations('.image-carousel-viewport--card', 'margin')).toEqual([]);
    expect(declarations('.image-carousel-image--card', 'border-radius')).toEqual(['0']);
  });

  test('the text block opens with 8px and its pieces are 16px apart', () => {
    expect(declarations('.thing-card-body', 'padding')).toEqual(['var(--spacing-2-xs) 0 0']);
  });

  test('the title is 24px bold, 1.2 high, -0.2px', () => {
    expect(declarations('.thing-card-headline', 'font-size')).toEqual([
      'var(--fontsize-heading-m)',
    ]);
    expect(declarations('.thing-card-headline', 'font-weight')).toEqual(['700']);
    expect(declarations('.thing-card-headline', 'line-height')).toEqual(['1.2']);
    expect(declarations('.thing-card-headline', 'letter-spacing')).toEqual(['-0.2px']);
  });

  test('the description is 16/24 Regular, still cut at two lines', () => {
    expect(declarations('.thing-card-description', 'font-size')).toEqual([
      'var(--fontsize-body-m)',
    ]);
    expect(declarations('.thing-card-description', 'line-height')).toEqual(['24px']);
    expect(declarations('.thing-card-description', 'font-weight')).toEqual(['400']);
    expect(declarations('.thing-card-description', '-webkit-line-clamp')).toEqual(['2']);
  });

  test('the date and author line stays 16/24 in black-60', () => {
    expect(declarations('.thing-card-meta', 'font-size')).toEqual(['var(--fontsize-body-m)']);
    expect(declarations('.thing-card-meta', 'line-height')).toEqual(['24px']);
    expect(declarations('.thing-card-meta', 'color')).toEqual(['var(--color-black-60)']);
  });

  test('the attributes: 8px above and below, 8px between rows, an icon 8px from a 16/24 text', () => {
    expect(declarations('.thing-card .thing-card-info', 'padding')).toEqual([
      'var(--spacing-2-xs) 0',
    ]);
    expect(declarations('.thing-card .thing-card-info', 'gap')).toEqual(['var(--spacing-2-xs)']);
    expect(declarations('.thing-card .thing-card-info-row', 'gap')).toEqual([
      'var(--spacing-2-xs)',
    ]);
    expect(declarations('.thing-card .thing-card-info-row', 'font-size')).toEqual([
      'var(--fontsize-body-m)',
    ]);
    expect(declarations('.thing-card .thing-card-info-row', 'line-height')).toEqual(['24px']);
    expect(declarations('.thing-card-info-row svg', 'width')).toEqual(['24px']);
    expect(declarations('.thing-card-info-label', 'font-weight')).toEqual(['700']);
  });

  test('a thing’s page keeps reading the same rows at 18/28 with 12px to the text', () => {
    expect(declarations('.thing-card-info-row', 'font-size')).toEqual(['var(--fontsize-body-l)']);
    expect(declarations('.thing-card-info-row', 'line-height')).toEqual(['28px']);
    expect(declarations('.thing-card-info-row', 'gap')).toEqual(['var(--spacing-xs)']);
  });
});

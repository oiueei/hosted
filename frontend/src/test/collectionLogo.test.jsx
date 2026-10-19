import { describe, test, expect } from 'vitest';
import { declarations, declarationsInMedia } from './cssRules';

/**
 * The collection's logo is one column of the card grid in width and its own
 * proportion in height; under 992px it opens the content, from 992px it takes the
 * last column at the top right and the text keeps to the columns before it. jsdom
 * paints nothing, so this pins what the stylesheet declares and where.
 */
const AT_992 = '(min-width: 992px)';

describe('the grid’s columns', () => {
  test('are 1, 2, 3 and 4 at the HDS breakpoints', () => {
    expect(declarations(':root', '--grid-columns')).toEqual(['1', '2', '3', '4']);
    expect(declarationsInMedia('(min-width: 768px)', ':root', '--grid-columns')).toEqual(['2']);
    expect(declarationsInMedia(AT_992, ':root', '--grid-columns')).toEqual(['3']);
    expect(declarationsInMedia('(min-width: 1248px)', ':root', '--grid-columns')).toEqual(['4']);
  });

  test('one column is the content minus the gaps between columns, over the columns', () => {
    // 320: 288 · 768: (720 - 24) / 2 = 348 · 992: (944 - 48) / 3 = 298.66 · 1248: (1200 - 72) / 4 = 282
    const [column] = declarations(':root', '--grid-column');
    expect(column.replace(/\s+/g, ' ')).toBe(
      'calc( (100% - (var(--grid-columns) - 1) * var(--page-margin)) / var(--grid-columns) )'
    );
  });
});

describe('the logo', () => {
  test('is as wide as a column and as tall as its proportion gives, never cropped', () => {
    expect(declarations('.hero-logo', 'width')).toEqual(['var(--grid-column)']);
    expect(declarations('.hero-logo', 'height')).toEqual(['auto']);
    expect(declarations('.hero-logo', 'object-fit')).toEqual([]);
  });

  test('is the last column, top right, from 992px, and in flow above the title before it', () => {
    expect(declarationsInMedia(AT_992, '.form-hero--collection .hero-logo', 'float')).toEqual([
      'right',
    ]);
    // The one float rule is the one in the query: below 992px it is a block, on the left,
    // above the title.
    expect(declarations('.form-hero--collection .hero-logo', 'float')).toEqual(['right']);
    expect(declarations('.hero-logo', 'display')).toEqual(['block']);
    // The float is held in the hero's height only from 992px.
    expect(
      declarationsInMedia(AT_992, '.form-hero--collection .form-hero-content', 'display')
    ).toEqual(['flow-root']);
  });

  test('its top is the title’s: the title has no margin above it beside the logo', () => {
    expect(
      declarationsInMedia(
        AT_992,
        '.form-hero--collection .form-hero-content > .hero-logo + .form-hero-title',
        'margin-top'
      )
    ).toEqual(['0']);
  });

  test('the text keeps to the columns before the logo’s, whether there is a logo or not', () => {
    const text =
      '.form-hero--collection .form-hero-content > :not(.hero-corners):not(.back-link):not(.hero-logo)';
    const [maxWidth] = declarationsInMedia(AT_992, text, 'max-width');
    // (columns - 1) columns and the gaps between them: 621.33 at 992, 894 at 1248.
    expect(maxWidth.replace(/\s+/g, ' ')).toBe(
      'calc( (var(--grid-columns) - 1) * var(--grid-column) + (var(--grid-columns) - 2) * var(--page-margin) )'
    );
    expect(declarations(text, 'max-width')).toHaveLength(1);
  });
});

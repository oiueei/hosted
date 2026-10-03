import { readFileSync } from 'node:fs';
import { describe, test, expect } from 'vitest';

/**
 * The contract of the table-cell classes in App.css (CA, 2026-10-03). jsdom does no
 * layout, so — in the manner of `heroCornerLayout.test.jsx` — what is pinned is
 * what the pages put in the DOM (their own tests: the class on the cell) and what
 * the rule declares, here. The rendering is for a browser.
 *
 *  - `.table-status-cell` (U13): the type `Tag` over the `StatusLabel`. In a bare
 *    column every child stretched to the column's width, so both labels filled it
 *    and `Tag`'s centred text and `StatusLabel`'s left text disagreed on screen.
 */
const css = readFileSync('src/App.css', 'utf8').replace(/\/\*[\s\S]*?\*\//g, '');

/** The declaration blocks of every rule whose selector list names `selector`. */
function rulesFor(selector) {
  return [...css.matchAll(/([^{}]+)\{([^{}]*)\}/g)]
    .filter(([, list]) =>
      list
        .split(',')
        .map((s) => s.trim())
        .includes(selector)
    )
    .map(([, , body]) => body);
}

const declared = (body, property) =>
  new RegExp(`(?:^|[;\\s])${property}\\s*:\\s*([^;]+)`).exec(body)?.[1]?.trim();

const declarations = (selector, property) =>
  rulesFor(selector)
    .map((body) => declared(body, property))
    .filter((value) => value !== undefined);

describe('.table-status-cell', () => {
  test('stacks its labels in a column, each as wide as its own word', () => {
    expect(declarations('.table-status-cell', 'display')).toEqual(['flex']);
    expect(declarations('.table-status-cell', 'flex-direction')).toEqual(['column']);
    // The line that keeps them from stretching: the default, `stretch`, is what
    // made both fill the column.
    expect(declarations('.table-status-cell', 'align-items')).toEqual(['flex-start']);
  });

  test('keeps a gap between them', () => {
    expect(declarations('.table-status-cell', 'gap')).toEqual(['var(--spacing-2-xs)']);
  });
});

describe('.table-cell-lines', () => {
  test('the lines of a cell touch, and are small', () => {
    expect(declarations('.table-cell-lines p', 'margin')).toEqual(['0']);
    expect(declarations('.table-cell-lines p', 'font-size')).toEqual(['var(--fontsize-body-s)']);
  });

  test('each kind of line has its grey, and the note its italic', () => {
    expect(declarations('.table-cell-line--muted', 'color')).toEqual(['var(--color-black-60)']);
    expect(declarations('.table-cell-line--faint', 'color')).toEqual(['var(--color-black-50)']);
    expect(declarations('.table-cell-line--none', 'color')).toEqual(['var(--color-black-40)']);
    expect(declarations('.table-cell-line--note', 'color')).toEqual(['var(--color-black-70)']);
    expect(declarations('.table-cell-line--note', 'font-style')).toEqual(['italic']);
  });
});

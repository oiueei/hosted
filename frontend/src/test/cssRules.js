import { readFileSync } from 'node:fs';

/**
 * Reading rules out of `App.css`, for the tests that pin a stylesheet contract.
 * jsdom does no layout, so a CSS fix is tested by what the rule declares and where
 * (inside which media query) — the manner of `heroCornerLayout.test.jsx` — plus
 * what the components put in the DOM. The comments are stripped so a word in one
 * cannot stand in for a declaration.
 */
export const css = readFileSync('src/App.css', 'utf8').replace(/\/\*[\s\S]*?\*\//g, '');

/** The declaration blocks of every rule in `source` whose selector list names `selector`. */
export function rulesIn(source, selector) {
  return [...source.matchAll(/([^{}]+)\{([^{}]*)\}/g)]
    .filter(([, list]) =>
      list
        .split(',')
        .map((s) => s.trim())
        .includes(selector)
    )
    .map(([, , body]) => body);
}

/** The same, over the whole stylesheet — rules inside a media query included. */
export const rulesFor = (selector) => rulesIn(css, selector);

/** What sits between the braces of every `@media <query> {…}` block (braces balanced). */
export function mediaBlocks(query) {
  const head = `@media ${query} {`;
  const blocks = [];
  for (let from = css.indexOf(head); from !== -1; from = css.indexOf(head, from)) {
    let depth = 1;
    let i = from + head.length;
    while (depth > 0 && i < css.length) {
      if (css[i] === '{') depth += 1;
      else if (css[i] === '}') depth -= 1;
      i += 1;
    }
    blocks.push(css.slice(from + head.length, i - 1));
    from = i;
  }
  return blocks;
}

/** The value a block declares for `property`, or undefined. */
export const declared = (body, property) =>
  new RegExp(`(?:^|[;\\s])${property}\\s*:\\s*([^;]+)`).exec(body)?.[1]?.trim();

/** Every value `selector` declares for `property`, anywhere in the stylesheet. */
export const declarations = (selector, property) =>
  rulesFor(selector)
    .map((body) => declared(body, property))
    .filter((value) => value !== undefined);

/** Every value `selector` declares for `property` inside the `@media <query>` blocks only. */
export const declarationsInMedia = (query, selector, property) =>
  mediaBlocks(query).flatMap((block) =>
    rulesIn(block, selector)
      .map((body) => declared(body, property))
      .filter((value) => value !== undefined)
  );

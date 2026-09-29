import { describe, test, expect } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';

/**
 * "All buttons across the app use theeeme colors" (frontend/CLAUDE.md) is true only
 * for as long as every HDS `<Button>` carries the theeeme's tokens, and a bare one
 * looks exactly right in development: it paints HDS's default blue, on a page whose
 * hero, background and neighbouring buttons are the viewer's own palette. Nothing
 * else in the suite can see it — the button works, is labelled, and passes axe.
 *
 * So the source is swept. Every `<Button …>` opening tag in `pages/` and
 * `components/` must carry one of the three ways to opt out of the default:
 *   - a `style=` (the theeeme's `btnStyle` / `btnSecondaryStyle`);
 *   - a spread `{...props}`, which brings its own style;
 *   - `variant="supplementary"` (the bare icon buttons) or `variant="danger"` (the
 *     account-erasure confirms, deliberately HDS's fixed red).
 *
 * **The tag is walked, not matched.** A regex like `<Button[^>]*>` stops at the `>` of
 * the `=>` in an `onClick={() => …}` and reads the rest of the props as absent, which
 * is a false alarm on every button with a handler. The walk keeps count of braces (and
 * of strings inside them), so only a `>` at the tag's top level ends it — and only what
 * sits at the top level counts, so a `style=` on an element nested in an attribute
 * (`icon={<Icon style={…} />}`) does not stand in for the button's own.
 */

const IGNORE_VARIANTS = new Set(['supplementary', 'danger']);

/** Every `<Button …>` opening tag in `source`, as `{ line, attrs }`. */
function buttonTags(source) {
  const found = [];
  const opening = /<Button(?=[\s/>])/g;
  for (const match of source.matchAll(opening)) {
    const lineStart = source.lastIndexOf('\n', match.index) + 1;
    // A tag inside a comment (`// <Button …>`, a JSDoc line, `{/* … */}`) is prose.
    if (/\/\/|\/\*|^\s*\*/.test(source.slice(lineStart, match.index))) continue;

    let depth = 0;
    let quote = null; // the quote of a string being read, at any depth
    let top = ''; // the tag's top level only: attributes, with each {…} folded to a marker
    let i = match.index + '<Button'.length;
    for (; i < source.length; i += 1) {
      const ch = source[i];
      if (quote) {
        if (ch === '\\') i += 1;
        else if (ch === quote) quote = null;
        if (depth === 0) top += ch;
        continue;
      }
      if (ch === '"' || ch === "'" || (ch === '`' && depth > 0)) {
        quote = ch;
        if (depth === 0) top += ch;
        continue;
      }
      if (ch === '{') {
        if (depth === 0)
          top += source
            .slice(i + 1)
            .trimStart()
            .startsWith('...')
            ? '{SPREAD}'
            : '{}';
        depth += 1;
        continue;
      }
      if (ch === '}') {
        depth -= 1;
        continue;
      }
      if (depth === 0) {
        if (ch === '>') break;
        top += ch;
      }
    }
    found.push({
      line: source.slice(0, match.index).split('\n').length,
      hasStyle: /(^|\s)style=/.test(top),
      hasSpread: top.includes('{SPREAD}'),
      variant: /(?:^|\s)variant="([^"]*)"/.exec(top)?.[1] ?? null,
    });
  }
  return found;
}

const isThemed = (tag) => tag.hasStyle || tag.hasSpread || IGNORE_VARIANTS.has(tag.variant);

describe('the walk over an opening tag', () => {
  const bare = (source) => buttonTags(source).filter((tag) => !isThemed(tag));

  test('a handler’s arrow is not the end of the tag — the style after it is seen', () => {
    expect(bare('<Button onClick={() => go()} style={btnStyle}>Go</Button>')).toEqual([]);
  });

  test('a bare button is caught, across lines and with an arrow in its handler', () => {
    const source = `
      <Button
        size="small"
        onClick={() => reload()}
      >
        Retry
      </Button>`;
    expect(bare(source).map((tag) => tag.line)).toEqual([2]);
  });

  test('a style on something nested in an attribute is not the button’s own', () => {
    expect(bare('<Button icon={<Icon style={{ color: "x" }} />}>Go</Button>')).toHaveLength(1);
  });

  test('a string that holds a brace or a > does not derail the count', () => {
    expect(bare(`<Button label="a > b" onClick={() => say('}')} style={s}>Go</Button>`)).toEqual(
      []
    );
    expect(bare(`<Button label="a > b" onClick={() => say('}')}>Go</Button>`)).toHaveLength(1);
  });

  test('a template literal inside an expression is read as one string', () => {
    expect(bare('<Button onClick={() => go(`${a}}`)} style={s}>Go</Button>')).toEqual([]);
  });

  test('a spread, or one of the two written variants, is themed', () => {
    expect(bare('<Button {...props}>Go</Button>')).toEqual([]);
    expect(bare('<Button variant="supplementary">Go</Button>')).toEqual([]);
    expect(bare('<Button variant="danger" onClick={x}>Go</Button>')).toEqual([]);
  });

  test('other variants are not an excuse: a secondary needs the theeeme too', () => {
    expect(bare('<Button variant="secondary">Go</Button>')).toHaveLength(1);
  });

  test('ButtonLink is a different component, and a commented tag is not a tag', () => {
    expect(buttonTags('<ButtonLink to="/x">Go</ButtonLink>')).toEqual([]);
    expect(buttonTags('  // <Button onClick={x}>\n * replaces <Link><Button/></Link>')).toEqual([]);
    expect(buttonTags('{/* <Button onClick={x}> */}')).toEqual([]);
  });
});

function sourceFiles(dir, found = []) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) sourceFiles(full, found);
    else if (/\.jsx$/.test(entry.name) && !entry.name.includes('.test.')) found.push(full);
  }
  return found;
}

describe('every HDS Button in the app paints in the viewer’s theeeme', () => {
  test('no bare <Button> in pages/ or components/', () => {
    const files = [
      ...sourceFiles(path.join('src', 'pages')),
      ...sourceFiles(path.join('src', 'components')),
    ];
    expect(files.length).toBeGreaterThan(50);

    let examined = 0;
    const offenders = [];
    for (const file of files) {
      for (const tag of buttonTags(fs.readFileSync(file, 'utf8'))) {
        examined += 1;
        if (!isThemed(tag)) offenders.push(`${file}:${tag.line}`);
      }
    }

    // The walk found the buttons: an empty sweep would pass for the wrong reason.
    expect(examined).toBeGreaterThan(80);
    expect(offenders).toEqual([]);
  });
});

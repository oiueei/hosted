import { readFileSync } from 'node:fs';
import { describe, test, expect } from 'vitest';
import { rulesFor } from './cssRules';

// A `###` used to come out smaller than the text around it: `.markdown-text` had
// no heading styles and the browser puts an h5 at 83%. jsdom does no layout, so
// the contract is pinned by what the stylesheet declares.

const tokens = readFileSync('node_modules/hds-design-tokens/lib/all.css', 'utf8');
const tokenRem = (name) => {
  const m = tokens.match(new RegExp(`--${name}:\\s*([\\d.]+)rem`));
  expect(m, `HDS token ${name}`).not.toBeNull();
  return Number(m[1]);
};

/** The font size, in rem, a heading's own rule declares (an `1em` is the text's own size, 1). */
function sizeOf(tag) {
  const body = rulesFor(`.markdown-text ${tag}`).find((b) => /font-size/.test(b));
  expect(body, `a font-size for .markdown-text ${tag}`).toBeDefined();
  const value = body.match(/font-size:\s*([^;]+);/)[1].trim();
  if (value === '1em') return 1;
  return tokenRem(value.match(/var\(--(fontsize-[a-z-]+)\)/)[1]);
}

describe('headings inside Markdown text', () => {
  test('h2 > h3 > h4 > h5, and no heading is smaller than the text', () => {
    const [h2, h3, h4, h5] = ['h2', 'h3', 'h4', 'h5'].map(sizeOf);
    expect(h2).toBeGreaterThan(h3);
    expect(h3).toBeGreaterThan(h4);
    expect(h4).toBeGreaterThan(h5);
    expect(h5).toBeGreaterThanOrEqual(1);
  });

  test('every heading is bold and has contained margins', () => {
    const body = rulesFor('.markdown-text h2').join('');
    expect(body).toMatch(/font-weight:\s*700/);
    expect(body).toMatch(/margin:\s*var\(--spacing-s\) 0 var\(--spacing-2-xs\)/);
  });

  test('a heading that opens the text has no gap above it', () => {
    for (const tag of ['h2', 'h3', 'h4', 'h5']) {
      const rule = rulesFor(`.markdown-text > ${tag}:first-child`).join('');
      expect(rule, tag).toMatch(/margin-top:\s*0/);
    }
  });
});

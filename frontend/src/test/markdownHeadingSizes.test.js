import { describe, test, expect } from 'vitest';
import { rulesFor } from './cssRules';

// A `###` used to come out smaller than the text around it: `.markdown-text` had
// no heading styles and the browser puts an h5 at 83%. jsdom does no layout, so
// the contract is pinned by what the stylesheet declares.
//
// The sizes are compared in `em`, as multiples of the text around the heading.
// They used to be HDS `rem` tokens checked against `1em` as if `1em` were always
// `1rem`; over the 18px text of the hero and of a bio, heading-xs (18px) and
// `1em` were the same size, so `##` and `###` looked alike there.

/** A heading's font size as a multiple of the text it sits in (its `em`). */
function sizeOf(tag) {
  const body = rulesFor(`.markdown-text ${tag}`).find((b) => /font-size/.test(b));
  expect(body, `a font-size for .markdown-text ${tag}`).toBeDefined();
  const value = body.match(/font-size:\s*([^;]+);/)[1].trim();
  const em = value.match(/^([\d.]+)em$/);
  expect(em, `.markdown-text ${tag} sizes itself in em, not "${value}"`).not.toBeNull();
  return Number(em[1]);
}

describe('headings inside Markdown text', () => {
  test('h2 > h3 > h4 > h5, and no heading is smaller than the text', () => {
    const [h2, h3, h4, h5] = ['h2', 'h3', 'h4', 'h5'].map(sizeOf);
    expect(h2).toBeGreaterThan(h3);
    expect(h3).toBeGreaterThan(h4);
    expect(h4).toBeGreaterThan(h5);
    expect(h5).toBeGreaterThanOrEqual(1);
  });

  test('no heading is sized with a rem or an HDS font-size token', () => {
    for (const tag of ['h2', 'h3', 'h4', 'h5']) {
      const body = rulesFor(`.markdown-text ${tag}`).join('');
      expect(body, tag).not.toMatch(/font-size:\s*[^;]*rem/);
      expect(body, tag).not.toMatch(/font-size:\s*var\(--fontsize-/);
    }
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

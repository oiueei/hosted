import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, test, expect } from 'vitest';

// Safari before 16.4 (iOS 16.0–16.3) cannot parse a regular expression with a
// lookbehind, `(?<=…)` or `(?<!…)`. It is a SyntaxError when the file is *read*,
// so on those phones the whole module that holds MarkdownText fails to load —
// every description, bio and legal page with it, not just the italics. jsdom
// parses lookbehind happily, so no rendering test can see this: the source is
// read instead.
const SOURCE = readFileSync(
  path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../components/MarkdownText.jsx'),
  'utf8'
);

describe('MarkdownText.jsx carries no lookbehind', () => {
  test('the file read is the Markdown renderer', () => {
    // A moved or renamed file must not leave this guard passing over nothing.
    expect(SOURCE.length).toBeGreaterThan(1000);
    expect(SOURCE).toContain('function renderEmphasis');
  });

  test.each([['(?<='], ['(?<!']])('no %s in the source', (lookbehind) => {
    const at = SOURCE.indexOf(lookbehind);
    expect(
      at,
      `MarkdownText.jsx contains a lookbehind (${lookbehind}) near ` +
        `"${SOURCE.slice(Math.max(0, at - 30), at + 30)}". Safari before 16.4 cannot ` +
        'parse it and does not load the file at all. Capture the edge in a group ' +
        'instead, e.g. /(^|\\W)\\*…/ with "$1" in the replacement.'
    ).toBe(-1);
  });
});

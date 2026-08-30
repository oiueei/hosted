import { render, screen } from '@testing-library/react';
import { describe, test, expect } from 'vitest';
import { readFileSync, readdirSync } from 'node:fs';
import path from 'node:path';
import StatusRegion from './StatusRegion';

/**
 * The one property that makes this work is that the region is in the DOM
 * *before* the message is. A live region only announces changes made inside a
 * region that already existed, so `{result && <StatusRegion>…</StatusRegion>}`
 * looks identical on screen, passes axe, and announces nothing — the exact
 * failure this component was written to end.
 */
describe('StatusRegion', () => {
  test('is there before there is anything to say', () => {
    render(<StatusRegion>{null}</StatusRegion>);

    const region = screen.getByRole('status');
    expect(region).toBeInTheDocument();
    expect(region).toBeEmptyDOMElement();
  });

  test('the message lands inside it, rather than beside it', () => {
    const { rerender } = render(<StatusRegion>{null}</StatusRegion>);
    rerender(
      <StatusRegion>
        <p>Saved</p>
      </StatusRegion>
    );

    expect(screen.getByRole('status')).toHaveTextContent('Saved');
  });

  test('role="status" is polite, which is what these messages want', () => {
    // Not `alert`: they answer something the reader just did, so they can wait
    // for the current utterance. `role="status"` also carries aria-live=polite
    // and aria-atomic implicitly, so nothing else has to be spelled out.
    render(<StatusRegion>hi</StatusRegion>);
    expect(screen.getByRole('status')).toHaveAttribute('role', 'status');
  });
});

function jsxFiles(dir, acc = []) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) jsxFiles(full, acc);
    else if (entry.name.endsWith('.jsx') && !entry.name.includes('.test.')) acc.push(full);
  }
  return acc;
}

describe('no StatusRegion is rendered conditionally', () => {
  test('every one of them is unconditional, or it announces nothing', () => {
    const offenders = [];
    for (const file of jsxFiles('src')) {
      const source = readFileSync(file, 'utf8');
      // `x && <StatusRegion`, `x ? <StatusRegion`, `: <StatusRegion` — every way
      // of making the region itself appear at the same moment as its content.
      for (const m of source.matchAll(/(&&|\?|:)\s*\(?\s*<StatusRegion\b/g)) {
        offenders.push(`${file}:${source.slice(0, m.index).split('\n').length}`);
      }
    }
    expect(offenders).toEqual([]);
  });

  test('the sweep is looking at a real tree, not an empty one', () => {
    const withRegion = jsxFiles('src').filter((f) =>
      readFileSync(f, 'utf8').includes('<StatusRegion>')
    );
    expect(withRegion.length).toBeGreaterThan(8);
  });
});

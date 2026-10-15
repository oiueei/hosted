import { render } from '@testing-library/react';
import { Table } from 'hds-react';
import { describe, test, expect } from 'vitest';
import { rulesFor, declared, css } from './cssRules';

/**
 * A table named only for screen readers must not reserve room on screen. jsdom does
 * no layout, so what is pinned is the contract: the rule that takes the room away
 * reaches the caption HDS paints, and it takes away everything HDS gives a caption.
 */
const SELECTOR = css.match(/caption:has\([^)]*\)/)?.[0];

const renderTable = (caption) =>
  render(
    <Table
      dense
      indexKey="id"
      caption={caption}
      cols={[{ key: 'name', headerName: 'Name' }]}
      rows={[{ id: 'a', name: 'Lala' }]}
    />
  );

const captionOf = (caption) => renderTable(caption).container.querySelector('caption');

describe('a table caption that only screen readers see', () => {
  test('the rule that flattens it declares no margin, no padding and no line height', () => {
    const [body] = rulesFor(SELECTOR);
    expect(body).toBeDefined();
    expect(declared(body, 'margin')).toBe('0');
    expect(declared(body, 'padding')).toBe('0');
    expect(declared(body, 'background')).toBe('none');
    expect(declared(body, 'line-height')).toBe('0');
  });

  test('the rule reaches the caption HDS paints around an sr-only title', () => {
    const caption = captionOf(<span className="sr-only">My requests</span>);
    expect(caption.matches(SELECTOR)).toBe(true);
  });

  test('a caption people can read is not flattened', () => {
    const caption = captionOf(<span>My requests</span>);
    expect(caption.matches(SELECTOR)).toBe(false);
  });

  test('a caption with visible text beside an sr-only part is not flattened', () => {
    const caption = captionOf(
      <>
        <span className="sr-only">Table:</span>
        <span>My requests</span>
      </>
    );
    expect(caption.matches(SELECTOR)).toBe(false);
  });
});

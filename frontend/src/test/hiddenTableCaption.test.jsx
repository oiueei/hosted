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

const renderTable = () =>
  render(
    <Table
      dense
      indexKey="id"
      caption={<span className="sr-only">My requests</span>}
      cols={[{ key: 'name', headerName: 'Name' }]}
      rows={[{ id: 'a', name: 'Lala' }]}
    />
  );

describe('a table caption that only screen readers see', () => {
  test('the rule that flattens it declares no margin, no padding and no line height', () => {
    const [body] = rulesFor(SELECTOR);
    expect(body).toBeDefined();
    expect(declared(body, 'margin')).toBe('0');
    expect(declared(body, 'padding')).toBe('0');
    expect(declared(body, 'background')).toBe('none');
    expect(declared(body, 'line-height')).toBe('0');
  });

  test('the rule reaches the sr-only text wherever HDS nests it in the caption', () => {
    const { container } = renderTable();
    const caption = container.querySelector('caption');
    const hidden = caption.querySelector('.sr-only');
    expect(hidden).not.toBeNull();

    // Walk down by only-children, as `:has(… .sr-only:only-child)` does, since
    // jsdom's selector engine may not evaluate `:has()`.
    let node = caption;
    while (node !== hidden.parentElement) {
      expect(node.children).toHaveLength(1);
      node = node.children[0];
    }
    expect(hidden.parentElement.children).toHaveLength(1);

    // The descendant form — no `>` — is what matches both nestings of HDS.
    expect(SELECTOR).toBe('caption:has(.sr-only:only-child)');
  });
});

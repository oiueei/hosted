import { Table } from 'hds-react';
import useMediaQuery from '../hooks/useMediaQuery';

// Below `breakpoint-m`, the same cut as every other mobile-only rule in the app.
const PHONE = '(max-width: 767px)';

/** The words inside a React node: what a `caption` made of a `sr-only` span says. */
function textOf(node) {
  if (node == null || typeof node === 'boolean') return '';
  if (typeof node === 'string' || typeof node === 'number') return String(node);
  if (Array.isArray(node)) return node.map(textOf).join('');
  return textOf(node.props?.children);
}

/**
 * The request tables and "My groups" as one component: the HDS `Table` it always
 * was above 768px, and below it **one card per row** (CA, 2026-10-04, after
 * screenshots from an iPhone).
 *
 * On a phone each column of a `Table` is about 100px wide: names broke word by
 * word, the status labels were cut off on the right, and the ✓ ⊗ buttons sat off
 * the screen with nothing to say the table scrolls sideways. A card gives every
 * cell the whole width instead.
 *
 * It takes what the `Table` takes — `cols`, `rows`, `indexKey`, `caption`, and any
 * other `Table` prop, which are handed on untouched — so a page swaps `<Table>` for
 * this and keeps its columns. **The cards are built from the same
 * `cols[].transform`**: what a card says about a row is written once, in the
 * column, not twice. Two optional keys on a column say how its card differs:
 *
 * - `cardTransform(row)` — what to paint in the card instead of `transform(row)`.
 *   For the actions column, where the table has icon buttons that name themselves
 *   in a tooltip and a card has room for the words.
 * - `cardLabel: true` — print the column's `headerName` and a colon in front of its
 *   content ("Run by: …"). The first column heads the card, and most of the others
 *   explain themselves, so this is the exception.
 *
 * In a card, the first column comes first and the rest follow one under another,
 * in the table's order — the actions column is last in all three tables. A column
 * whose content is `null` for a row (the actions of a settled request) leaves out
 * its place in that card, label included.
 *
 * **One or the other, never both**: the card list replaces the table in the DOM
 * rather than the stylesheet hiding one of them, so a screen reader never hears a
 * row twice. The list is named by the caption, since a `<ul>` has no `<caption>`.
 * Without `window.matchMedia` (jsdom) it is the table.
 */
export default function ResponsiveTable({ cols, rows, indexKey, caption, ...tableProps }) {
  const phone = useMediaQuery(PHONE);

  if (!phone) {
    return (
      <div className="table-wrap">
        <Table
          // The card-only keys stay out of HDS's hands.
          cols={cols.map(({ cardTransform, cardLabel, ...col }) => col)}
          rows={rows}
          indexKey={indexKey}
          caption={caption}
          {...tableProps}
        />
      </div>
    );
  }

  return (
    <ul className="table-cards" aria-label={textOf(caption)}>
      {rows.map((row) => (
        <li key={row[indexKey]} className="table-card">
          {cols.map((col) => {
            const content = (col.cardTransform ?? col.transform)(row);
            if (content == null || content === false) return null;
            return (
              <div
                key={col.key}
                className={
                  col.cardLabel ? 'table-card-field table-card-field--labelled' : undefined
                }
              >
                {col.cardLabel && <span className="table-card-label">{col.headerName}:</span>}
                {content}
              </div>
            );
          })}
        </li>
      ))}
    </ul>
  );
}

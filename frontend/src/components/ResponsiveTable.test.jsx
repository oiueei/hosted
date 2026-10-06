import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { describe, test, expect, afterEach, vi } from 'vitest';
import { axe, toHaveNoViolations } from 'jest-axe';
import ResponsiveTable from './ResponsiveTable';
import { mockMatchMedia, PHONE } from '../test/matchMedia';

expect.extend(toHaveNoViolations);

/**
 * A table on a desktop, one card per row on a phone. The columns
 * are the pages' own shape in miniature: a first column that names the row, one
 * that wants its header in front, one that is null for some rows, and an actions
 * column with a different face in a card.
 */
const rows = [
  { id: 'A', name: 'Drill', team: 'Oriol and 2 more', open: true },
  { id: 'B', name: 'Ladder', team: '', open: false },
];

const cols = [
  {
    key: 'name',
    headerName: 'Thing',
    transform: (row) => <a href={`#${row.id}`}>{row.name}</a>,
  },
  {
    key: 'team',
    headerName: 'Run by',
    cardLabel: true,
    transform: (row) => (row.team ? <p>{row.team}</p> : null),
  },
  {
    key: 'actions',
    headerName: <span className="sr-only">Actions</span>,
    transform: (row) => (row.open ? <span>icon for {row.name}</span> : null),
    cardTransform: (row) => (row.open ? <button type="button">Close {row.name}</button> : null),
  },
];

const renderTable = (props = {}) =>
  render(
    <MemoryRouter>
      <ResponsiveTable
        cols={cols}
        rows={rows}
        indexKey="id"
        caption={<span className="sr-only">Things on the shelf</span>}
        renderIndexCol={false}
        {...props}
      />
    </MemoryRouter>
  );

let media;
afterEach(() => media?.restore());

describe('ResponsiveTable on a desktop', () => {
  test('is the table it always was, in its scrolling wrapper, with no card list', () => {
    media = mockMatchMedia({ [PHONE]: false });
    const { container } = renderTable();

    expect(screen.getByRole('table', { name: 'Things on the shelf' })).toBeInTheDocument();
    expect(container.querySelector('.table-wrap table')).not.toBeNull();
    expect(screen.queryByRole('list')).toBeNull();
    // One body row per row, and the table's own face for the actions.
    expect(screen.getAllByRole('row')).toHaveLength(1 + rows.length);
    expect(screen.getByText('icon for Drill')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Close Drill' })).toBeNull();
  });

  test('is also the table where the browser has no matchMedia at all', () => {
    renderTable();

    expect(screen.getByRole('table')).toBeInTheDocument();
    expect(screen.queryByRole('list')).toBeNull();
  });
});

describe('ResponsiveTable on a phone', () => {
  test('is a list named by the caption, one item per row, and no table', () => {
    media = mockMatchMedia({ [PHONE]: true });
    const { container } = renderTable();

    const list = screen.getByRole('list', { name: 'Things on the shelf' });
    expect(within(list).getAllByRole('listitem')).toHaveLength(rows.length);
    expect(screen.queryByRole('table')).toBeNull();
    expect(container.querySelector('table')).toBeNull();
    expect(container.querySelector('.table-wrap')).toBeNull();
  });

  test('says what the columns say: the card is built from the same transforms', () => {
    media = mockMatchMedia({ [PHONE]: true });
    renderTable();

    const [drill] = screen.getAllByRole('listitem');
    expect(within(drill).getByRole('link', { name: 'Drill' })).toHaveAttribute('href', '#A');
    expect(within(drill).getByText('Oriol and 2 more')).toBeInTheDocument();
  });

  test('the first column heads the card and the others follow in the table order', () => {
    media = mockMatchMedia({ [PHONE]: true });
    renderTable();

    const [drill] = screen.getAllByRole('listitem');
    const order = [...drill.children].map((field) => field.textContent);
    expect(order).toEqual(['Drill', 'Run by:Oriol and 2 more', 'Close Drill']);
  });

  test('the actions column uses its card face, not the table one', () => {
    media = mockMatchMedia({ [PHONE]: true });
    renderTable();

    expect(screen.getByRole('button', { name: 'Close Drill' })).toBeInTheDocument();
    expect(screen.queryByText('icon for Drill')).toBeNull();
  });

  test('a column that asks for its header shows it with a colon; the others do not', () => {
    media = mockMatchMedia({ [PHONE]: true });
    renderTable();

    expect(screen.getByText('Run by:')).toBeInTheDocument();
    expect(screen.queryByText('Thing:')).toBeNull();
    expect(screen.queryByText('Actions:')).toBeNull();
  });

  test('a column that has nothing for a row leaves out its place, label included', () => {
    media = mockMatchMedia({ [PHONE]: true });
    renderTable();

    const [, ladder] = screen.getAllByRole('listitem');
    expect([...ladder.children].map((field) => field.textContent)).toEqual(['Ladder']);
    expect(within(ladder).queryByText('Run by:')).toBeNull();
  });

  test('a column with no card face of its own falls back to its transform', () => {
    media = mockMatchMedia({ [PHONE]: true });
    renderTable({ cols: cols.map(({ cardTransform, ...col }) => col) });

    expect(screen.getByText('icon for Drill')).toBeInTheDocument();
  });

  test('has no axe violations', async () => {
    media = mockMatchMedia({ [PHONE]: true });
    const { container } = renderTable();

    expect(await axe(container)).toHaveNoViolations();
  });
});

describe('ResponsiveTable across the breakpoint', () => {
  test('swaps the table for the list and back, never painting both', () => {
    media = mockMatchMedia({ [PHONE]: false });
    renderTable();
    expect(screen.getByRole('table')).toBeInTheDocument();

    media.set(PHONE, true);
    expect(screen.queryByRole('table')).toBeNull();
    expect(screen.getByRole('list')).toBeInTheDocument();

    media.set(PHONE, false);
    expect(screen.getByRole('table')).toBeInTheDocument();
    expect(screen.queryByRole('list')).toBeNull();
  });

  test('does not hand the card-only keys to the HDS table', () => {
    media = mockMatchMedia({ [PHONE]: false });
    const warn = vi.spyOn(console, 'error').mockImplementation(() => {});
    const { container } = renderTable();

    expect(container.querySelector('[cardlabel], [cardtransform]')).toBeNull();
    expect(warn).not.toHaveBeenCalled();
    warn.mockRestore();
  });
});

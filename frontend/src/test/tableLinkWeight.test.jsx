import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { describe, test, expect, afterEach } from 'vitest';
import ResponsiveTable from '../components/ResponsiveTable';
import ButtonLink from '../components/ButtonLink';
import { mockMatchMedia, PHONE } from './matchMedia';
import { css, rulesFor, declared } from './cssRules';

/**
 * The text links of the three tables — the thing's name in /my-bookings and
 * /owner-bookings, the group's name and "Leave the group" in "My groups" — are bold.
 * One rule, for both forms of `ResponsiveTable` (the desktop
 * table and the phone's cards), hung from the component's own class so it reaches no
 * other table, and leaving out anything with a button's style.
 *
 * jsdom does no layout: this pins what the rule declares and the selector it is hung
 * from, and that the DOM the pages paint is what the selector is written against.
 * Each page's own test pins that its links are inside the class.
 */
const SELECTOR = ".responsive-table a:not([class*='hds-button'])";

describe('the rule', () => {
  test('exists once, in one place, and declares a bold weight', () => {
    const rules = rulesFor(SELECTOR);

    expect(rules).toHaveLength(1);
    expect(declared(rules[0], 'font-weight')).toBe('700');
  });

  test('sets the weight and nothing else: "Leave the group" keeps its size and its grey', () => {
    const [body] = rulesFor(SELECTOR);

    expect(body.split(';').filter((line) => line.trim())).toHaveLength(1);
    // …and that size and grey are still its own rule's.
    const [muted] = rulesFor('.table-cell-link--muted');
    expect(declared(muted, 'font-size')).toBe('var(--fontsize-body-s)');
    expect(declared(muted, 'color')).toBe('var(--color-black-60)');
    expect(declared(muted, 'font-weight')).toBeUndefined();
  });

  test('names the component’s class and the links, and not the buttons', () => {
    expect(SELECTOR.startsWith('.responsive-table ')).toBe(true);
    expect(SELECTOR).toContain(' a');
    expect(SELECTOR).toContain(":not([class*='hds-button'])");
  });

  test('no rule hangs it from .table-wrap or from the plain tables, which other pages share', () => {
    expect(rulesFor('.table-wrap a')).toEqual([]);
    expect(rulesFor('.table-wrap')).toHaveLength(1);
    expect(declared(rulesFor('.table-wrap')[0], 'font-weight')).toBeUndefined();
    // The bold weight is not given to the links of every cell of the app either.
    expect(css).not.toMatch(/(^|[\s,}])table a\s*[,{]/);
    expect(css).not.toMatch(/\.table-cell-lines a\s*[,{]/);
  });
});

describe('what the selector is written against', () => {
  let media;
  afterEach(() => media?.restore());

  const cols = [
    { key: 'name', headerName: 'Thing', transform: (row) => <a href={`#${row.id}`}>{row.name}</a> },
    {
      key: 'actions',
      headerName: 'Actions',
      transform: (row) => <ButtonLink to={`/things/${row.id}`}>Go to {row.name}</ButtonLink>,
    },
  ];
  const renderTable = () =>
    render(
      <MemoryRouter>
        <ResponsiveTable
          cols={cols}
          rows={[{ id: 'A', name: 'Drill' }]}
          indexKey="id"
          caption={<span className="sr-only">Things</span>}
          renderIndexCol={false}
        />
      </MemoryRouter>
    );

  test('on a desktop the component’s class is on the table’s wrapper, with its scrolling', () => {
    media = mockMatchMedia({ [PHONE]: false });
    const { container } = renderTable();

    const wrapper = container.querySelector('.responsive-table');
    expect(wrapper).toHaveClass('table-wrap');
    expect(wrapper.querySelector('table')).not.toBeNull();
    expect(container.querySelectorAll('.responsive-table')).toHaveLength(1);
  });

  test('on a phone it is on the list of cards', () => {
    media = mockMatchMedia({ [PHONE]: true });
    const { container } = renderTable();

    const list = container.querySelector('.responsive-table');
    expect(list.tagName).toBe('UL');
    expect(list).toHaveClass('table-cards');
    expect(container.querySelectorAll('.responsive-table')).toHaveLength(1);
  });

  test.each([
    ['desktop', false],
    ['phone', true],
  ])('on a %s a text link matches the selector and a ButtonLink does not', (_form, phone) => {
    media = mockMatchMedia({ [PHONE]: phone });
    renderTable();

    expect(screen.getByRole('link', { name: 'Drill' }).matches(SELECTOR)).toBe(true);
    // A ButtonLink is an <a> too, and it is excluded by the class HDS gives it: this
    // ties the selector to the real component rather than to a guess at its markup.
    expect(screen.getByRole('link', { name: 'Go to Drill' }).matches(SELECTOR)).toBe(false);
  });

  test('a link outside the component’s class does not match', () => {
    media = mockMatchMedia({ [PHONE]: false });
    render(
      <div className="table-wrap">
        <a href="#x">Another table’s link</a>
      </div>
    );

    expect(screen.getByRole('link').matches(SELECTOR)).toBe(false);
  });
});

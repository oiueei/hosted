import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { describe, test, expect, beforeEach } from 'vitest';
import PageLayout from './PageLayout';
import { declarations, declarationsInMedia } from '../test/cssRules';

/**
 * `heroActions` (X1, CA 2026-10-04): buttons in the hero, after the title and the
 * description, in a `.button-row-wide` of their own. Only a thing's page uses it
 * for now, and its test says which buttons; this one is the slot itself and the
 * stylesheet that makes it behave, since jsdom applies no CSS.
 */
const renderLayout = (props) =>
  render(
    <MemoryRouter>
      <PageLayout title="A title" description="A description" {...props}>
        <p>content</p>
      </PageLayout>
    </MemoryRouter>
  );

beforeEach(() => localStorage.clear());

describe('PageLayout — heroActions', () => {
  test('are painted in the hero after the title and the description, in a wide row', () => {
    const { container } = renderLayout({
      heroActions: (
        <>
          <button type="button">First</button>
          <button type="button">Second</button>
        </>
      ),
    });

    const row = container.querySelector('.form-hero-content .hero-actions');
    expect(row).toHaveClass('button-row-wide');
    expect([...row.children].map((c) => c.textContent)).toEqual(['First', 'Second']);
    const title = screen.getByRole('heading', { name: 'A title' });
    const description = screen.getByText('A description');
    // Document order: title, description, then the buttons.
    expect(title.compareDocumentPosition(description)).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
    expect(description.compareDocumentPosition(row)).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
    // …and not in the content below the hero.
    expect(container.querySelector('.page-container .hero-actions')).toBeNull();
  });

  test('without any, there is no row at all', () => {
    const { container } = renderLayout({});

    expect(container.querySelector('.hero-actions')).toBeNull();
    expect(container.querySelector('.form-hero .button-row-wide')).toBeNull();
  });

  test('the same for null — what a page passes when it has nothing to decide', () => {
    const { container } = renderLayout({ heroActions: null });

    expect(container.querySelector('.hero-actions')).toBeNull();
  });
});

describe('the hero actions stylesheet', () => {
  const DESKTOP = '(min-width: 768px)';

  test('the row wraps and keeps its buttons at the top, so a panel can take a line of its own', () => {
    expect(declarations('.hero-actions', 'flex-wrap')).toEqual(['wrap']);
    expect(declarations('.hero-actions', 'align-items')).toEqual(['flex-start']);
  });

  test('an opened InlineConfirm goes last, under the buttons, the whole width of the row from 768px', () => {
    const panel = '.hero-actions > .thing-report-confirm';
    expect(declarations(panel, 'order')).toEqual(['1']);
    // A flex-basis of the whole line means something in a row only; in the column
    // of a phone `align-self` is what gives it the width.
    expect(declarations(panel, 'align-self')).toEqual(['stretch']);
    expect(declarations(panel, 'flex')).toEqual(declarationsInMedia(DESKTOP, panel, 'flex'));
    expect(declarationsInMedia(DESKTOP, panel, 'flex')).toEqual(['1 1 100%']);
  });

  test('the confirm panel has its own text colour, not the hero text colour', () => {
    // A light surface wherever it opens: on a dark theeeme, text taken from the
    // hero would be white on near-white.
    const colours = declarations('.thing-report-confirm', 'color');
    expect(colours).toEqual(['var(--color-black-90)']);
    expect(colours.join(' ')).not.toMatch(/hero-text-color/);
  });
});

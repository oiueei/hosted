import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter, Routes, Route, useLocation } from 'react-router';
import { describe, test, expect } from 'vitest';
import ButtonLink from './ButtonLink';

/**
 * `ButtonLink` replaced 25 `<Link><Button>` pairs, so what it does is what a
 * quarter of the app's navigation now does.
 */
function renderLink(props = {}) {
  return render(
    <MemoryRouter initialEntries={['/']}>
      <Routes>
        <Route
          path="/"
          element={
            <main>
              <button type="button">before</button>
              <ButtonLink to="/somewhere" {...props}>
                Go
              </ButtonLink>
              <button type="button">after</button>
            </main>
          }
        />
        <Route path="/somewhere" element={<div data-testid="arrived">arrived</div>} />
      </Routes>
    </MemoryRouter>
  );
}

const TAB_STOPS = 'a[href]:not([tabindex="-1"]), button:not([disabled])';

describe('ButtonLink', () => {
  test('is one link, and one tab stop — not a link wrapping a button', () => {
    const { container } = renderLink();

    expect(screen.getByRole('link', { name: 'Go' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Go' })).not.toBeInTheDocument();
    // before, the link, after — three, where the old shape gave four.
    expect(container.querySelectorAll(TAB_STOPS)).toHaveLength(3);
  });

  test('wears the real HDS button classes, not a hand-rolled lookalike', () => {
    renderLink();
    // `useButtonStyles` swaps in `hds-button` + its variant; the names are hashed
    // per build, so match the stable part rather than the whole string.
    expect(screen.getByRole('link', { name: 'Go' }).className).toMatch(/hds-button/);
  });

  test('the theeeme tokens reach the element, which is what colours it', () => {
    renderLink({ style: { '--background-color': 'var(--color-summer)' } });

    expect(screen.getByRole('link', { name: 'Go' }).getAttribute('style')).toContain(
      '--background-color: var(--color-summer)'
    );
  });

  test('fullWidth is ours, since HDS Link has no such prop', () => {
    renderLink({ fullWidth: true });
    expect(screen.getByRole('link', { name: 'Go' })).toHaveClass('button-link--full');
  });

  test('a plain click navigates without leaving the app', () => {
    renderLink();

    fireEvent.click(screen.getByRole('link', { name: 'Go' }));
    expect(screen.getByTestId('arrived')).toBeInTheDocument();
  });

  test('it passes navigation state on, the way Link did', () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <Routes>
          <Route
            path="/"
            element={
              <ButtonLink to="/somewhere" state={{ backLabel: 'Home' }}>
                Go
              </ButtonLink>
            }
          />
          <Route path="/somewhere" element={<Landed />} />
        </Routes>
      </MemoryRouter>
    );

    fireEvent.click(screen.getByRole('link', { name: 'Go' }));
    expect(screen.getByTestId('state')).toHaveTextContent('Home');
  });

  // The whole point of a real link over a button with an onClick. Each of these
  // must reach the browser untouched, or "open in a new tab" quietly stops
  // working — the exact capability this change was meant to win back.
  test.each([
    ['cmd', { metaKey: true }],
    ['ctrl', { ctrlKey: true }],
    ['shift', { shiftKey: true }],
    ['alt', { altKey: true }],
    ['middle', { button: 1 }],
  ])('a %s click is left to the browser', (_name, modifier) => {
    renderLink();

    const notPrevented = fireEvent.click(screen.getByRole('link', { name: 'Go' }), modifier);

    expect(notPrevented).toBe(true);
    expect(screen.queryByTestId('arrived')).not.toBeInTheDocument();
  });

  test('the href is real, so the browser has somewhere to open', () => {
    renderLink();
    expect(screen.getByRole('link', { name: 'Go' })).toHaveAttribute('href', '/somewhere');
  });
});

function Landed() {
  // MemoryRouter keeps its own stack, so the state comes from the router, not
  // from window.history.
  return <div data-testid="state">{useLocation().state?.backLabel}</div>;
}

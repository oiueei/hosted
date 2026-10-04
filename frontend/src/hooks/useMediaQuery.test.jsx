import { render, screen } from '@testing-library/react';
import { describe, test, expect, afterEach } from 'vitest';
import useMediaQuery from './useMediaQuery';
import { mockMatchMedia, PHONE } from '../test/matchMedia';

/**
 * The hook behind every "paint one thing below 768px, another above" decision
 * (`ResponsiveTable`). The harness prints what it reads, which is all a component
 * ever does with it.
 */
function Reading({ query = PHONE }) {
  return <p>{useMediaQuery(query) ? 'matches' : 'does not match'}</p>;
}

let media;
afterEach(() => media?.restore());

describe('useMediaQuery', () => {
  test('reads the answer the browser gives, on the first render', () => {
    media = mockMatchMedia({ [PHONE]: true });
    render(<Reading />);

    expect(screen.getByText('matches')).toBeInTheDocument();
  });

  test('a query that does not match reads false', () => {
    media = mockMatchMedia({ [PHONE]: false });
    render(<Reading />);

    expect(screen.getByText('does not match')).toBeInTheDocument();
  });

  test('follows the window across the breakpoint, both ways', () => {
    media = mockMatchMedia({ [PHONE]: false });
    render(<Reading />);
    expect(screen.getByText('does not match')).toBeInTheDocument();

    media.set(PHONE, true);
    expect(screen.getByText('matches')).toBeInTheDocument();

    media.set(PHONE, false);
    expect(screen.getByText('does not match')).toBeInTheDocument();
  });

  test('asks the browser about the query it was given, not another one', () => {
    media = mockMatchMedia({ [PHONE]: true, '(min-width: 992px)': false });
    render(<Reading query="(min-width: 992px)" />);

    expect(screen.getByText('does not match')).toBeInTheDocument();
  });

  test('stops listening when the component goes away', () => {
    media = mockMatchMedia({ [PHONE]: true });
    const { unmount } = render(<Reading />);
    expect(media.listening(PHONE)).toBe(1);

    unmount();

    expect(media.listening(PHONE)).toBe(0);
  });

  test('with no matchMedia in the environment it reads false, and does not throw', () => {
    // jsdom's own state: no stub installed.
    expect(window.matchMedia).toBeUndefined();
    render(<Reading />);

    expect(screen.getByText('does not match')).toBeInTheDocument();
  });
});

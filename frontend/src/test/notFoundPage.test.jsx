import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { describe, test, expect, beforeEach } from 'vitest';
import NotFoundPage from '../pages/NotFoundPage';

/**
 * The 404 page offers one way out. Like every loose action button it sits in a
 * `.button-row-wide`, so on a phone it is the width of the screen and on a
 * desktop the width of its own text (CA, 2026-10-04).
 */
describe('NotFoundPage', () => {
  beforeEach(() => localStorage.clear());

  test('a signed-out visitor is sent to the login, in a wide row', () => {
    render(
      <MemoryRouter>
        <NotFoundPage />
      </MemoryRouter>
    );

    const exit = screen.getByRole('link', { name: 'Go to login' });
    expect(exit).toHaveAttribute('href', '/login');
    expect(exit.parentElement).toHaveClass('button-row-wide');
  });

  test('a signed-in one is sent home, in the same wide row', () => {
    localStorage.setItem('userCode', 'USR001');
    render(
      <MemoryRouter>
        <NotFoundPage />
      </MemoryRouter>
    );

    const exit = screen.getByRole('link', { name: 'Go to homepage' });
    expect(exit).toHaveAttribute('href', '/');
    expect(exit.parentElement).toHaveClass('button-row-wide');
  });
});

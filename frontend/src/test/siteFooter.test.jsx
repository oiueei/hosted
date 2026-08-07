import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { describe, test, expect } from 'vitest';

import SiteFooter from '../components/SiteFooter';

/**
 * The colophon carries the only two doors a signed-out reader has.
 *
 * `/welcome` was made public so a stranger could read what OIUEEI is, and
 * `/legal` is the page the privacy claims tell you to go and check — but every
 * link to either sat behind a login or on a page only a joiner sees. Someone
 * reading a public collection, the top of the entire funnel, could reach
 * neither. These links are what makes those two public routes reachable.
 */
describe('SiteFooter', () => {
  test('offers the two public doors on every page, signed in or not', () => {
    render(<MemoryRouter><SiteFooter /></MemoryRouter>);

    expect(screen.getByRole('link', { name: /what oiueei is/i })).toHaveAttribute('href', '/welcome');
    expect(screen.getByRole('link', { name: /privacy & legal/i })).toHaveAttribute('href', '/legal');
  });

  test('still says where it was made', () => {
    render(<MemoryRouter><SiteFooter /></MemoryRouter>);
    expect(screen.getByText(/Zona Franca/)).toBeInTheDocument();
  });
});

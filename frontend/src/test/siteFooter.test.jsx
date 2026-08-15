import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { describe, test, expect } from 'vitest';

import SiteFooter from '../components/SiteFooter';

/**
 * The colophon carries the public doors a signed-out reader has.
 *
 * `/legal` is the page the privacy claims tell you to go and check, and every
 * link to it used to sit behind a login or on a page only a joiner sees:
 * someone reading a public collection, the top of the entire funnel, could not
 * reach it. This link is what makes that public route reachable.
 *
 * The second link is a deployment's own "what this is" page, and upstream there
 * is none — so the footer must show one link, not a dead one.
 */
describe('SiteFooter', () => {
  test('always reaches the legal page, from any page, signed in or not', () => {
    render(<MemoryRouter><SiteFooter /></MemoryRouter>);

    expect(screen.getByRole('link', { name: /privacy & legal/i })).toHaveAttribute('href', '/legal');
  });

  test('offers no about link when this deployment has no such page', () => {
    render(<MemoryRouter><SiteFooter /></MemoryRouter>);

    // A footer link to a route that 404s is worse than one link fewer.
    expect(screen.queryByRole('link', { name: /what oiueei is/i })).not.toBeInTheDocument();
    expect(document.querySelector('a[href="/welcome"]')).toBeNull();
  });

  test('still says where it was made', () => {
    render(<MemoryRouter><SiteFooter /></MemoryRouter>);
    expect(screen.getByText(/Zona Franca/)).toBeInTheDocument();
  });
});

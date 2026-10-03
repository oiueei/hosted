import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { describe, test, expect, vi } from 'vitest';

import SiteFooter from '../components/SiteFooter';
import { declarations, declarationsInMedia } from './cssRules';

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
    render(
      <MemoryRouter>
        <SiteFooter />
      </MemoryRouter>
    );

    expect(screen.getByRole('link', { name: /privacy & legal/i })).toHaveAttribute(
      'href',
      '/legal'
    );
  });

  test('offers no about link when the deployment has no such page', async () => {
    /* The module is mocked rather than read, so this holds on a deployment that
       *does* have an about page — where the real export is a path and asserting
       its absence would fail on the branch this indirection exists to serve. */
    vi.resetModules();
    vi.doMock('../deployment', () => ({ aboutPath: null }));
    const { default: Footer } = await import('../components/SiteFooter');

    render(
      <MemoryRouter>
        <Footer />
      </MemoryRouter>
    );

    // A footer link to a route that 404s is worse than one link fewer.
    expect(screen.queryByRole('link', { name: /what oiueei is/i })).not.toBeInTheDocument();
    expect(document.querySelector('a[href="/welcome"]')).toBeNull();
    vi.doUnmock('../deployment');
  });

  test('still says where it was made', () => {
    render(
      <MemoryRouter>
        <SiteFooter />
      </MemoryRouter>
    );
    expect(screen.getByText(/Zona Franca/)).toBeInTheDocument();
  });
});

/**
 * One line from 768px (CA, 2026-10-03): "Privacy & legal · Made with ♥︎ in …", the
 * doors and the colophon text side by side; under 768px the two lines it always
 * was. jsdom does no layout, so this pins what the component puts in the DOM and
 * what App.css declares and where — the rendering is for a browser.
 */
describe('SiteFooter — one line from 768px', () => {
  const renderFooter = () => {
    const { container } = render(
      <MemoryRouter>
        <SiteFooter />
      </MemoryRouter>
    );
    const footer = container.querySelector('footer');
    return {
      footer,
      nav: footer.querySelector('nav'),
      sep: footer.querySelector('.site-footer-sep'),
    };
  };

  test('the separator is decoration: aria-hidden, a child of the footer, outside the nav', () => {
    const { footer, nav, sep } = renderFooter();

    expect(sep).not.toBeNull();
    expect(sep).toHaveAttribute('aria-hidden', 'true');
    expect(sep.parentElement).toBe(footer);
    expect(nav.contains(sep)).toBe(false);
    expect(sep.textContent.trim()).toBe('·');
  });

  test('the text stays outside the nav, after the separator; the nav holds only links', () => {
    const { footer, nav, sep } = renderFooter();

    expect(nav.textContent).not.toMatch(/Zona Franca/);
    expect(nav.querySelectorAll('a')).toHaveLength(1);
    expect(
      sep.compareDocumentPosition(footer.lastChild) & Node.DOCUMENT_POSITION_FOLLOWING
    ).toBeTruthy();
    expect(footer.lastChild.textContent).toMatch(/Zona Franca/);
  });

  test('upstream, with no about link, the line is the legal door then the text', () => {
    const { footer } = renderFooter();

    expect(footer.textContent.replace(/\s+/g, ' ').trim()).toMatch(
      /^Privacy & legal · Made with .*Zona Franca/
    );
  });

  test('from 768px the footer is a centred flex row, aligned on the middles of its items', () => {
    // The links are 44px tall and the text is not: without align-items the text
    // would sit on the baseline of the row, off the links' middle.
    expect(declarationsInMedia('(min-width: 768px)', '.site-footer', 'display')).toEqual(['flex']);
    expect(declarationsInMedia('(min-width: 768px)', '.site-footer', 'align-items')).toEqual([
      'center',
    ]);
    expect(declarationsInMedia('(min-width: 768px)', '.site-footer', 'justify-content')).toEqual([
      'center',
    ]);
    // And outside the query it is not one: two lines, as before.
    expect(declarations('.site-footer', 'display')).toEqual(['flex']);
  });

  test('the separator is hidden below 768px and shown from there', () => {
    // On two lines it would hang at the end of the first. One `none` outside the
    // query and one `inline` inside it — nothing else says where it shows.
    expect(declarations('.site-footer-sep', 'display')).toEqual(['none', 'inline']);
    expect(declarationsInMedia('(min-width: 768px)', '.site-footer-sep', 'display')).toEqual([
      'inline',
    ]);
  });
});

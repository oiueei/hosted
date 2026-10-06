import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { describe, test, expect, vi } from 'vitest';

import SiteFooter from '../components/SiteFooter';
import { declarations, declarationsInMedia, rulesFor, declared } from './cssRules';

// This file is about what a deployment with no forms of its own hosted elsewhere shows
// — the app's own contact page, `VITE_FEEDBACK_URL`, the server's request address. A
// core test cannot assume what `deployment/` holds, so the
// `externalForms` a deployment may have are switched off here by stubbing the helper
// that reads them; `externalForms.test.jsx` pins them on, with the module mocked.
vi.mock('../utils/externalForms', () => ({ externalFormUrl: () => null }));

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
    vi.doMock('../deployment', () => ({ aboutPath: null, externalForms: null }));
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
 * "Contact us" is the third door: it was a speech-bubble icon in
 * the corner of every hero, and there were too many icons up there. It sits in the
 * `<nav>` after the legal link, on every page and for everybody, signed in or not.
 */
describe('SiteFooter — "Contact us"', () => {
  const links = () => {
    const { container } = render(
      <MemoryRouter>
        <SiteFooter />
      </MemoryRouter>
    );
    return [...container.querySelectorAll('footer nav a')];
  };

  test('is a link to /contact inside the nav', () => {
    const contact = links().find((link) => link.textContent === 'Contact us');

    expect(contact).toHaveAttribute('href', '/contact');
  });

  test('comes after the legal link', () => {
    const hrefs = links().map((link) => link.getAttribute('href'));

    expect(hrefs.indexOf('/contact')).toBeGreaterThan(hrefs.indexOf('/legal'));
    expect(hrefs.indexOf('/legal')).not.toBe(-1);
  });

  test('is the last door of the nav: the colophon text follows it', () => {
    const all = links();

    expect(all[all.length - 1]).toHaveAttribute('href', '/contact');
  });
});

/**
 * One line from 768px: "Privacy & legal · Contact us · Made with ♥︎
 * in …", the doors and the colophon text side by side; under 768px the two lines it
 * always was. jsdom does no layout, so this pins what the component puts in the DOM
 * and what App.css declares and where — the rendering is for a browser.
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
      // The page's own column, inside the footer's full-width background.
      inner: footer.querySelector('.site-footer-inner'),
      nav: footer.querySelector('nav'),
      sep: footer.querySelector('.site-footer-sep'),
    };
  };

  test('the separator is decoration: aria-hidden, in the column, outside the nav', () => {
    const { inner, nav, sep } = renderFooter();

    expect(sep).not.toBeNull();
    expect(sep).toHaveAttribute('aria-hidden', 'true');
    expect(sep.parentElement).toBe(inner);
    expect(nav.contains(sep)).toBe(false);
    expect(sep.textContent.trim()).toBe('·');
  });

  test('the text stays outside the nav, after the separator; the nav holds only links', () => {
    const { inner, nav, sep } = renderFooter();

    expect(nav.textContent).not.toMatch(/Zona Franca/);
    // Links, and the aria-hidden dot between two of them where the deployment has
    // an about page — never a count: that is one link upstream and two on a
    // deployment, and this file runs on both.
    expect(nav.querySelectorAll('a').length).toBeGreaterThan(0);
    for (const child of nav.children) {
      expect(child.tagName === 'A' || child.getAttribute('aria-hidden') === 'true').toBe(true);
    }
    expect(
      sep.compareDocumentPosition(inner.lastChild) & Node.DOCUMENT_POSITION_FOLLOWING
    ).toBeTruthy();
    expect(inner.lastChild.textContent).toMatch(/Zona Franca/);
  });

  /* What the line reads depends on whether the deployment has an about page, so
     both shapes mock the module rather than read it — the same reason as "offers
     no about link" above: read for real, one of them would fail on the branch
     that has the other shape. */
  const lineWith = async (aboutPath) => {
    vi.resetModules();
    vi.doMock('../deployment', () => ({ aboutPath, externalForms: null }));
    try {
      const { default: Footer } = await import('../components/SiteFooter');
      const { container } = render(
        <MemoryRouter>
          <Footer />
        </MemoryRouter>
      );
      return container.querySelector('footer').textContent.replace(/\s+/g, ' ').trim();
    } finally {
      vi.doUnmock('../deployment');
    }
  };

  test('upstream, with no about link, the line is the legal door, contact, then the text', async () => {
    expect(await lineWith(null)).toMatch(/^Privacy & legal · Contact us · Made with .*Zona Franca/);
  });

  test('a deployment with an about page puts it first, then legal, contact and the text', async () => {
    expect(await lineWith('/about-us')).toMatch(
      /^What OIUEEI is · Privacy & legal · Contact us · Made with .*Zona Franca/
    );
  });

  test('from 768px the column is a flex row from the left, aligned on the middles of its items', () => {
    // The links are 44px tall and the text is not: without align-items the text
    // would sit on the baseline of the row, off the links' middle.
    const inner = '.site-footer-inner';
    expect(declarationsInMedia('(min-width: 768px)', inner, 'display')).toEqual(['flex']);
    expect(declarationsInMedia('(min-width: 768px)', inner, 'align-items')).toEqual(['center']);
    // From the left of the column — not centred any more.
    expect(declarationsInMedia('(min-width: 768px)', inner, 'justify-content')).toEqual([
      'flex-start',
    ]);
    // And outside the query it is not a flex row: two lines, as before.
    expect(declarations(inner, 'display')).toEqual(['flex']);
  });

  test('the footer is aligned to the left of the column, not centred', () => {
    expect(declarations('.site-footer', 'text-align')).toEqual(['left']);
  });

  test('its column is the page’s: the same width, centring and side padding as .page-container', () => {
    const [maxWidth] = declarations('.site-footer-inner', 'max-width');
    const [margin] = declarations('.site-footer-inner', 'margin');
    const [padding] = declarations('.site-footer-inner', 'padding');

    expect(maxWidth).toBe(declarations('.page-container', 'max-width')[0]);
    expect(margin).toBe(declarations('.page-container', 'margin')[0]);
    expect(maxWidth).toBe('1248px');
    // `padding: top sides bottom`: the sides must be the page container's own.
    const sides = padding.split(/\s+/)[1];
    expect(sides).toBe(declarations('.page-container', 'padding')[0]);
  });

  test('the first link has no padding on its left, so its first letter is on the column’s vertical', () => {
    const [rule] = rulesFor('.site-footer-links a:first-child');

    expect(declared(rule, 'padding-left')).toBe('0');
    // The others keep the 2xs on both sides, which is what spaces them from the dot.
    expect(declarations('.site-footer-links a', 'padding')).toEqual(['0 var(--spacing-2-xs)']);
  });

  test('the links stay 44px tall', () => {
    expect(declarations('.site-footer-links a', 'min-height')).toEqual(['44px']);
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

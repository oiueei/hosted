import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router';
import { readFileSync, readdirSync } from 'node:fs';
import { vi, describe, test, expect, beforeEach } from 'vitest';

/**
 * The icon corner of the hero at 320px (2026-09-29). jsdom does no layout, so the
 * overflow itself cannot be measured here; what can be pinned is the contract the two
 * CSS fixes stand on, in the manner of the `padding-right` rule in
 * `CollectionPage.test.jsx`: that the selector matches the DOM the page really paints
 * (rename a class and the rule silently stops applying, nothing red), and that the
 * declarations the fix relies on are the ones in App.css.
 *
 *  1. The account menu's panel ran off the left of the screen. `.account-menu` was
 *     `position: relative`, which anchored the panel to its own trigger, and for a
 *     curator that trigger is the first of four icons. With no positioned ancestor of
 *     its own the panel anchors to `.hero-corners`, whose right edge is the content
 *     column's.
 *  2. A long "← {collection name}" ran underneath the icons. `.hero-corners` is absolute
 *     and reserves nothing, so the back link is capped by the width the corner can take.
 */

window.scrollTo = vi.fn();

vi.mock('../services/api', async (importOriginal) => ({
  ...(await importOriginal()),
  apiFetch: vi.fn(),
  getCsrfToken: vi.fn(() => 'mock-csrf'),
}));

import { apiFetch } from '../services/api';
import PageLayout from '../components/PageLayout';
import CollectionPage from '../pages/CollectionPage';

// ── App.css, as rules ──────────────────────────────────────────────────
const css = readFileSync('src/App.css', 'utf8').replace(/\/\*[\s\S]*?\*\//g, '');

/** The declaration blocks of every rule in `source` whose selector list names `selector`. */
function rulesIn(source, selector) {
  return [...source.matchAll(/([^{}]+)\{([^{}]*)\}/g)]
    .filter(([, list]) =>
      list
        .split(',')
        .map((s) => s.trim())
        .includes(selector)
    )
    .map(([, , body]) => body);
}

/** The same, over the whole stylesheet — rules inside a media query included. */
const rulesFor = (selector) => rulesIn(css, selector);

/** What sits between the braces of every `@media <query> {…}` block (braces balanced). */
function mediaBlocks(query) {
  const head = `@media ${query} {`;
  const blocks = [];
  for (let from = css.indexOf(head); from !== -1; from = css.indexOf(head, from)) {
    let depth = 1;
    let i = from + head.length;
    while (depth > 0 && i < css.length) {
      if (css[i] === '{') depth += 1;
      else if (css[i] === '}') depth -= 1;
      i += 1;
    }
    blocks.push(css.slice(from + head.length, i - 1));
    from = i;
  }
  return blocks;
}

/** The value a block declares for `property`, or undefined. */
const declared = (body, property) =>
  new RegExp(`(?:^|[;\\s])${property}\\s*:\\s*([^;]+)`).exec(body)?.[1]?.trim();

const declarations = (selector, property) =>
  rulesFor(selector)
    .map((body) => declared(body, property))
    .filter((value) => value !== undefined);

// ── The DOM the rules have to match ────────────────────────────────────
beforeEach(() => {
  localStorage.clear();
  localStorage.setItem('userCode', 'ABC123');
  vi.clearAllMocks();
});

const renderHero = () =>
  render(
    <MemoryRouter>
      <PageLayout title="A hero" backTo="/collections/COL001" backLabel="Test Collection" />
    </MemoryRouter>
  );

const CURATED = {
  code: 'COL001',
  headline: 'Test Collection',
  description: '',
  status: 'ACTIVE',
  mode: 'PROPRIETARY',
  visibility: 'PRIVATE',
  owner: 'ABC123',
  owner_name: 'Test User',
  is_curator: true,
  language: '',
  thumbnail_url: '',
  tags: [],
  things: [],
  invites: [],
  co_owners: [],
};

describe('the account menu panel anchors to the corner row', () => {
  test('the panel sits in .account-menu, which sits directly in .hero-corners', () => {
    const { container } = renderHero();
    fireEvent.click(screen.getByRole('button', { name: /your account/i }));

    const panel = container.querySelector('.account-menu-panel');
    expect(panel).not.toBeNull();
    // Nothing between them for a positioning rule to hang on to but `.account-menu`
    // itself — which is why what that class declares matters.
    expect(panel.parentElement).toHaveClass('account-menu');
    expect(panel.parentElement.parentElement).toHaveClass('hero-corners');
  });

  test('.account-menu establishes no containing block of its own', () => {
    // Anything below would make the panel anchor to the trigger again. (`position` is
    // the one that was there; the rest are the other ways to become a containing block
    // for an absolutely positioned descendant.)
    const containingBlockMakers = [
      'position',
      'transform',
      'filter',
      'perspective',
      'contain',
      'will-change',
    ];
    for (const property of containingBlockMakers) {
      expect(declarations('.account-menu', property), property).toEqual([]);
    }
  });

  test('.hero-corners is the positioned ancestor, and the panel is pinned to its right edge', () => {
    expect(declarations('.hero-corners', 'position')).toEqual(['absolute']);
    expect(declarations('.account-menu-panel', 'position')).toEqual(['absolute']);
    expect(declarations('.account-menu-panel', 'right')).toEqual(['0']);
    // Whatever the row's width, the panel is never wider than the screen minus gutters.
    expect(declarations('.account-menu-panel', 'max-width')).toEqual([
      'calc(100vw - 2 * var(--spacing-s))',
    ]);
  });
});

describe('the back link keeps out from under the corner icons', () => {
  test('the rule names an element that sits beside the corner row in the hero', () => {
    const { container } = renderHero();

    const backLink = container.querySelector('.form-hero-content .back-link');
    expect(backLink).not.toBeNull();
    expect(backLink.parentElement).toHaveClass('form-hero-content');
    // The thing it has to make room for is its sibling in the same column.
    expect(backLink.parentElement.querySelector(':scope > .hero-corners')).not.toBeNull();
  });

  test('it is capped by the width the corner can take, plus a gap', () => {
    const caps = declarations('.form-hero-content .back-link', 'max-width');
    expect(caps).toEqual(['calc(100% - var(--hero-corners-width) - var(--spacing-xs))']);
  });

  test('that width is the widest corner there is, worked out again from the DOM and the rules', async () => {
    apiFetch.mockImplementation(() =>
      Promise.resolve({ ok: true, status: 200, json: async () => CURATED })
    );
    const { container } = render(
      <MemoryRouter initialEntries={['/collections/COL001']}>
        <Routes>
          <Route path="/collections/:code" element={<CollectionPage />} />
        </Routes>
      </MemoryRouter>
    );
    await screen.findByRole('combobox'); // the share menu: a curator's hero is loaded
    // A curator gets every control a hero can hold: account, collection, share.
    // The contact icon that was a fourth left for the footer on 2026-10-04.
    const controls = container.querySelector('.hero-corners').children.length;
    expect(controls).toBe(3);

    const [declaredWidth] = declarations('.form-hero-content', '--hero-corners-width');
    const [, count, size, gaps] =
      /^calc\((\d+) \* (\d+)px \+ (\d+) \* var\(--spacing-2-xs\)\)$/.exec(declaredWidth) ?? [];
    // Three controls, each as wide as the CSS says an icon control is, and the gaps
    // between them (one fewer) at the row's own `gap`.
    expect(Number(count)).toBe(controls);
    for (const selector of ['.account-menu-trigger', '.collection-menu-trigger', '.share-corner']) {
      expect(declarations(selector, 'width'), selector).toEqual([`${size}px`]);
    }
    expect(Number(gaps)).toBe(controls - 1);
    expect(declarations('.hero-corners', 'gap')).toEqual(['var(--spacing-2-xs)']);
  });
});

describe('the collection menu panel anchors to the corner row like the account menu', () => {
  test('the corner row reads account · collection · share, left to right', async () => {
    apiFetch.mockImplementation(() =>
      Promise.resolve({ ok: true, status: 200, json: async () => CURATED })
    );
    const { container } = render(
      <MemoryRouter initialEntries={['/collections/COL001']}>
        <Routes>
          <Route path="/collections/:code" element={<CollectionPage />} />
        </Routes>
      </MemoryRouter>
    );
    await screen.findByRole('combobox'); // a curator's hero has loaded

    // DOM order is visual order in a flex row: each control is the child that is,
    // or holds, its own marker.
    const markers = ['.account-menu', '.collection-menu', '.share-corner'];
    const order = [...container.querySelector('.hero-corners').children].map((child) =>
      markers.find((marker) => child.matches(marker) || child.querySelector(marker))
    );
    expect(order).toEqual(markers);
  });

  test('the panel sits in .collection-menu, which sits directly in .hero-corners', async () => {
    apiFetch.mockImplementation(() =>
      Promise.resolve({ ok: true, status: 200, json: async () => CURATED })
    );
    const { container } = render(
      <MemoryRouter initialEntries={['/collections/COL001']}>
        <Routes>
          <Route path="/collections/:code" element={<CollectionPage />} />
        </Routes>
      </MemoryRouter>
    );
    fireEvent.click(await screen.findByRole('button', { name: /collection options/i }));

    const panel = container.querySelector('.collection-menu-panel');
    expect(panel).not.toBeNull();
    expect(panel.parentElement).toHaveClass('collection-menu');
    expect(panel.parentElement.parentElement).toHaveClass('hero-corners');
  });

  test('.collection-menu establishes no containing block of its own', () => {
    // Same rule as .account-menu above: with one of its own, the panel would
    // anchor to its trigger again and run off a narrow screen.
    const containingBlockMakers = [
      'position',
      'transform',
      'filter',
      'perspective',
      'contain',
      'will-change',
    ];
    for (const property of containingBlockMakers) {
      expect(declarations('.collection-menu', property), property).toEqual([]);
    }
  });

  test("the panel is pinned to the row's right edge, never wider than the screen", () => {
    expect(declarations('.collection-menu-panel', 'position')).toEqual(['absolute']);
    expect(declarations('.collection-menu-panel', 'right')).toEqual(['0']);
    expect(declarations('.collection-menu-panel', 'max-width')).toEqual([
      'calc(100vw - 2 * var(--spacing-s))',
    ]);
  });
});

/**
 * The hero photo on a wide screen (CA, 2026-10-03). jsdom does no layout, so what
 * is pinned is the contract of the rule: `.hero-photo-wrap` is a background that
 * ran to the window's edge while the content column, centred from 1248px up, did
 * not; its right edge now comes in by the same centring sum `.hero-corners` uses.
 * It belongs inside `@media (min-width: 768px)` — below that the photo is a static
 * block on the phone, and an `inset` there would move a box that has no edges.
 */
describe('the hero photo ends at the content column on a wide screen', () => {
  const wide = '(min-width: 768px)';
  const photoRightIn = (blocks) =>
    blocks.flatMap((block) =>
      rulesIn(block, '.hero-photo-wrap')
        .map((body) => declared(body, 'right'))
        .filter((value) => value !== undefined)
    );

  test('.hero-photo-wrap declares its right edge inside the ≥768px query, and only there', () => {
    const inWide = photoRightIn(mediaBlocks(wide));

    expect(inWide).toHaveLength(1);
    // The one declaration in the whole stylesheet: a copy outside the query (or in
    // the phone's) would take the phone's stacked photo along with it.
    expect(declarations('.hero-photo-wrap', 'right')).toEqual(inWide);
  });

  test("it is the corner row's own centring sum, without the corner's gutter", () => {
    const [corner] = declarations('.hero-corners', 'right');
    expect(corner).toMatch(/ \+ var\(--spacing-s\)\)$/);

    const [photo] = photoRightIn(mediaBlocks(wide));
    expect(photo).toBe(corner.replace(/ \+ var\(--spacing-s\)\)$/, ')'));
    // And it is the sum that is 0 up to the column's own width.
    expect(photo).toBe('calc((100% - min(100%, 1248px)) / 2)');
  });

  test("the left edge (30%) is still the base rule's", () => {
    expect(declarations('.hero-photo-wrap', 'inset')).toContain('0 0 0 30%');
  });
});

/**
 * The contact icon is not in any hero (CA, 2026-10-04: "there are too many icons up
 * there"): "Contact us" is the site footer's third door. Pinned on the two heroes
 * that paint the corner for everybody — `PageLayout` and a curator's collection,
 * the fullest one — by what is inside `.hero-corners` and by what a hero links at
 * all, and by the source: nothing in `src/` names the old component.
 */
describe('no hero carries the contact icon', () => {
  const contactLinks = (root) => root.querySelectorAll('a[href="/contact"]');

  test('PageLayout’s hero links nowhere to /contact', () => {
    const { container } = renderHero();

    expect(container.querySelector('.hero-corners')).not.toBeNull();
    expect(contactLinks(container.querySelector('.form-hero'))).toHaveLength(0);
  });

  test('a curator’s collection hero, with every corner control, links nowhere to /contact', async () => {
    apiFetch.mockImplementation(() =>
      Promise.resolve({ ok: true, status: 200, json: async () => CURATED })
    );
    const { container } = render(
      <MemoryRouter initialEntries={['/collections/COL001']}>
        <Routes>
          <Route path="/collections/:code" element={<CollectionPage />} />
        </Routes>
      </MemoryRouter>
    );
    await screen.findByRole('combobox');

    expect(container.querySelector('.hero-corners').children).toHaveLength(3);
    expect(contactLinks(container.querySelector('.form-hero'))).toHaveLength(0);
  });

  test('nothing in the sources names the component or its rule any more', () => {
    const files = [];
    const walk = (dir) => {
      for (const entry of readdirSync(dir, { withFileTypes: true })) {
        const path = `${dir}/${entry.name}`;
        if (entry.isDirectory()) walk(path);
        else if (/\.(jsx?|css)$/.test(entry.name) && !/\.test\./.test(entry.name)) files.push(path);
      }
    };
    walk('src');

    const offenders = files.filter((file) =>
      /ContactCorner|contact-corner/.test(
        readFileSync(file, 'utf8')
          .replace(/\/\*[\s\S]*?\*\//g, '')
          .replace(/^\s*(\/\/|\*).*$/gm, '')
      )
    );
    expect(offenders).toEqual([]);
  });
});

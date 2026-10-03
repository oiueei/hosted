import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router';
import { readFileSync } from 'node:fs';
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

/** The declaration blocks of every rule whose selector list names `selector`. */
function rulesFor(selector) {
  return [...css.matchAll(/([^{}]+)\{([^{}]*)\}/g)]
    .filter(([, list]) =>
      list
        .split(',')
        .map((s) => s.trim())
        .includes(selector)
    )
    .map(([, , body]) => body);
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
    // A curator gets every control a hero can hold: account, collection, share,
    // contact.
    const controls = container.querySelector('.hero-corners').children.length;
    expect(controls).toBe(4);

    const [declaredWidth] = declarations('.form-hero-content', '--hero-corners-width');
    const [, count, size, gaps] =
      /^calc\((\d+) \* (\d+)px \+ (\d+) \* var\(--spacing-2-xs\)\)$/.exec(declaredWidth) ?? [];
    // Four controls, each as wide as the CSS says an icon control is, and the gaps
    // between them (one fewer) at the row's own `gap`.
    expect(Number(count)).toBe(controls);
    for (const selector of [
      '.contact-corner',
      '.account-menu-trigger',
      '.collection-menu-trigger',
      '.share-corner',
    ]) {
      expect(declarations(selector, 'width'), selector).toEqual([`${size}px`]);
    }
    expect(Number(gaps)).toBe(controls - 1);
    expect(declarations('.hero-corners', 'gap')).toEqual(['var(--spacing-2-xs)']);
  });
});

describe('the collection menu panel anchors to the corner row like the account menu', () => {
  test('the corner row reads account · collection · share · contact, left to right', async () => {
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
    const markers = ['.account-menu', '.collection-menu', '.share-corner', '.contact-corner'];
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

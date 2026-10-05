import { render, waitFor } from '@testing-library/react';
import { vi, describe, test, expect, beforeEach, afterEach } from 'vitest';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { css, rulesFor, declared, declarations } from './cssRules';

/**
 * The footer at the bottom of the visible screen, with no scroll to spare (G7, CA
 * 2026-10-05). `.form-page` had `min-height: 100vh` and the footer came after `<main>`,
 * so every page was a screen plus a footer: always a scroll, and the footer always just
 * under the first screen — worse on iOS, where `100vh` is taller than what is visible.
 * Now `#root` is a column as tall as the viewport, `<main>` takes what is left and is a
 * column itself, and the `.form-page` it holds fills it.
 *
 * jsdom does no layout, so — in the manner of `heroCornerLayout.test.jsx` — this pins
 * the contract: what the rules declare, and the DOM the rules are written against. How it
 * looks (a short page without scroll, a long one with the footer at its end, the iPhone
 * with no rebound and no strip of another colour under the footer) is for a browser.
 */

// App's mount effect primes the CSRF cookie against the real network; jsdom has no scrollTo.
globalThis.fetch = vi.fn(() =>
  Promise.resolve({ ok: false, status: 401, json: () => Promise.resolve({}) })
);
window.scrollTo = vi.fn();

beforeEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
  vi.resetModules();
  window.history.pushState({}, '', '/legal');
});
afterEach(() => {
  window.history.pushState({}, '', '/');
});

/** The one declaration block a selector has in the stylesheet (outside any media query). */
const only = (selector) => {
  const rules = rulesFor(selector);
  expect(rules, `${selector} should have exactly one rule`).toHaveLength(1);
  return rules[0];
};

describe('the container: #root is a column as tall as the viewport', () => {
  test('declares display flex, column direction, and min-height in vh then dvh', () => {
    const root = only('#root');

    expect(declared(root, 'display')).toBe('flex');
    expect(declared(root, 'flex-direction')).toBe('column');
    // Two lines on purpose: `100vh` for a browser that does not know `dvh`, then `100dvh`
    // after it, which one that does will take. In that order or the first is dead.
    const heights = [...root.matchAll(/min-height\s*:\s*([^;]+)/g)].map((m) => m[1].trim());
    expect(heights).toEqual(['100vh', '100dvh']);
  });

  test('is the one place that sets the viewport height', () => {
    // `.form-page` carried the other `100vh`; nothing else does, in CSS or inline.
    expect(css.match(/100vh/g)).toHaveLength(1);
    expect(css.match(/100dvh/g)).toHaveLength(1);

    const sources = [];
    const walk = (dir) => {
      for (const name of readdirSync(dir)) {
        const path = join(dir, name);
        if (statSync(path).isDirectory()) walk(path);
        else if (/\.(jsx?|css)$/.test(name) && !/\.test\.jsx?$/.test(name) && name !== 'App.css') {
          sources.push(path);
        }
      }
    };
    walk('src');
    // A comment may name the old `100vh` page (SiteFooter's did); code may not use it.
    const withoutComments = (text) =>
      text.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/.*$/gm, '$1');
    const inCode = sources.filter((path) =>
      /100d?vh/.test(withoutComments(readFileSync(path, 'utf8')))
    );
    expect(inCode).toEqual([]);
  });
});

describe('<main> takes what is left and is a column', () => {
  test('declares its flex, and is a column so the page inside it can fill it', () => {
    const main = only('main');

    expect(declared(main, 'flex')).toBe('1 0 auto');
    expect(declared(main, 'display')).toBe('flex');
    expect(declared(main, 'flex-direction')).toBe('column');
  });

  test('a bare .page-container under it is full width, because margin auto stops a column item stretching', () => {
    // The loading spinner and Home's offline banner are not inside a `.form-page`.
    const bare = only('main > .page-container');

    expect(declared(bare, 'width')).toBe('100%');
  });
});

describe('the page fills <main>, with no 100vh of its own', () => {
  test('.form-page no longer declares a min-height, and grows to fill', () => {
    const rules = rulesFor('.form-page');
    expect(rules).toHaveLength(1);

    expect(declarations('.form-page', 'min-height')).toEqual([]);
    expect(rules[0]).not.toMatch(/100d?vh/);
    expect(declared(rules[0], 'flex')).toBe('1 0 auto');
  });
});

describe('the App frame the rules are written against', () => {
  test('main and the footer are siblings in one container, the footer after main', async () => {
    const { default: App } = await import('../App');
    const { container } = render(<App />);

    await waitFor(() => expect(container.querySelector('footer.site-footer')).not.toBeNull());
    const main = container.querySelector('main#main');
    const footer = container.querySelector('footer.site-footer');

    // The same parent: in the real page it is `#root`, and it is the flex column.
    expect(main.parentElement).toBe(footer.parentElement);
    expect(main.nextElementSibling).toBe(footer);
    // The skip link is still the first thing in it, before `<main>`.
    const skip = container.querySelector('a.skip-link');
    expect(skip.parentElement).toBe(main.parentElement);
    expect(skip.compareDocumentPosition(main) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  test('the page inside <main> is a .form-page, the child the rules make fill it', async () => {
    const { default: App } = await import('../App');
    const { container } = render(<App />);

    await waitFor(() => expect(container.querySelector('main .form-page')).not.toBeNull());
    const page = container.querySelector('main .form-page');
    expect(page.parentElement).toBe(container.querySelector('main'));
  });

  test('the footer keeps its own colour and its row of links: it is not part of this change', async () => {
    const { default: App } = await import('../App');
    const { container } = render(<App />);

    await waitFor(() => expect(container.querySelector('footer.site-footer')).not.toBeNull());
    const footer = container.querySelector('footer.site-footer');
    // Painted inline with the viewer's theeeme when there is one (a signed-out reader
    // has none, so it falls back to the stylesheet's); the structure is what stays.
    expect(footer.querySelector('.site-footer-inner')).not.toBeNull();
    expect(footer.querySelector('nav.site-footer-links')).not.toBeNull();
  });
});

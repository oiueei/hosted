import { render, waitFor } from '@testing-library/react';
import { vi, describe, test, expect, beforeEach, afterEach } from 'vitest';

/**
 * `App.jsx` — the frame every page renders inside: the skip link, the focus and
 * scroll reset on navigation, and `html[lang]`.
 *
 * Its routes are covered elsewhere (`deployment.test.jsx` pins that a
 * deployment's own route mounts above the catch-all and that unknown paths still
 * reach the 404). What was unguarded is the pair of effects around them, both of
 * which carry a written rationale and neither of which any test exercised — so
 * the rationale was the only thing keeping them true.
 *
 * The one that is easiest to "fix" into a bug is the initial mount: focusing
 * `<main>` on load looks like the obviously complete version of a focus reset,
 * and it would make the skip link — which precedes `<main>` — unreachable by the
 * first forward Tab, quietly deleting the affordance for exactly the users it
 * exists for.
 */

// App's mount effect primes the CSRF cookie against the real network, and jsdom
// has no scrollTo. Both inert; the scrollTo spy is also an assertion target.
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

/** Navigate the way a real click does: push the entry, then let the router hear
 *  about it. `pushState` alone changes the URL without notifying BrowserRouter. */
function navigateTo(path) {
  window.history.pushState({}, '', path);
  window.dispatchEvent(new PopStateEvent('popstate'));
}

describe('the skip link', () => {
  test('is in the document, before main, pointing at it', async () => {
    const { default: App } = await import('../App');
    const { container } = render(<App />);

    const skip = container.querySelector('a.skip-link');
    expect(skip).not.toBeNull();
    expect(skip.getAttribute('href')).toBe('#main');

    // Order is the whole mechanism: a skip link after the content it skips is
    // decoration. DOCUMENT_POSITION_FOLLOWING = main comes after the link.
    const main = container.querySelector('#main');
    expect(skip.compareDocumentPosition(main) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  test('survives the first load with focus untouched, so it is the first tab stop', async () => {
    const { default: App } = await import('../App');
    const { container } = render(<App />);

    await waitFor(() => expect(container.querySelector('#main')).not.toBeNull());

    // Nothing has stolen focus into the page: the next Tab reaches the skip
    // link. If a focus reset ever runs on mount, this is the test that says so.
    expect(document.activeElement).not.toBe(container.querySelector('#main'));
    expect(window.scrollTo).not.toHaveBeenCalled();
  });
});

describe('navigating to another page', () => {
  test('moves focus into main and scrolls back to the top', async () => {
    const { default: App } = await import('../App');
    const { container } = render(<App />);

    const main = container.querySelector('#main');
    await waitFor(() => expect(main).not.toBeNull());

    navigateTo('/contact');

    // Both halves matter to a keyboard or screen-reader user: focus lands on the
    // new page's content rather than wherever the previous page left it, and the
    // viewport is not still parked halfway down the page they came from.
    await waitFor(() => expect(document.activeElement).toBe(main));
    expect(window.scrollTo).toHaveBeenCalledWith(0, 0);
  });

  test('renders the page that was navigated to', async () => {
    // Guards the navigation helper itself: a focus assertion would also pass on
    // a router that never heard the popstate and re-rendered nothing.
    const { default: App } = await import('../App');
    render(<App />);

    await waitFor(() => expect(document.title).toMatch(/legal|OIUEEI/i));

    navigateTo('/contact');

    await waitFor(() => expect(document.title).toMatch(/contact|contacto|contacte/i));
  });
});

describe('html[lang]', () => {
  test('follows the interface language, on load and on every change', async () => {
    const { default: App } = await import('../App');
    const { default: i18n } = await import('../i18n');
    render(<App />);

    await waitFor(() => expect(document.documentElement.lang).toBe(i18n.language));

    // The attribute is what tells a screen reader which pronunciation to use and
    // a translator which language it is reading; the picker changes the strings
    // whether or not anyone updates it.
    await i18n.changeLanguage('es');
    await waitFor(() => expect(document.documentElement.lang).toBe('es'));

    await i18n.changeLanguage('en');
    await waitFor(() => expect(document.documentElement.lang).toBe('en'));
  });
});

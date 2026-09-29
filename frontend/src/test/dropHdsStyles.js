/**
 * Drop the stylesheets `hds-react` injects into `<head>`, so a `*ByRole` query
 * on a form page costs milliseconds instead of ~0.45 s.
 *
 * `hds-react` writes its CSS into the document **when it is imported**: ~75
 * `<style>` tags, ~350 kB, ~1,700 rules, in every test file that renders one of
 * its components (`css: false` in `vite.config.js` does not reach them — they are
 * JS-injected). jsdom's `getComputedStyle` walks every rule for each element it
 * is asked about, and `getByRole(..., { name })` asks about every candidate and
 * its subtree to compute an accessible name. Measured on `EditCollectionPage`
 * (429 elements, 32 buttons), a name query right after any DOM change costs
 * 450-650 ms — with the sheets gone, 40 ms — and 55 of them were 90 % of that
 * file's test time (20.8 s of 23 s; `collectionForm.test.jsx`: 12.9 s of 16.3 s).
 * Under coverage on a loaded machine that is where the 20 s `testTimeout` was
 * brushed (a test of `EditCollectionPage` at 20 s, an axe test at 23 s).
 *
 * What it costs: nothing these files assert. jsdom does no layout, and what
 * hides an element here is the `hidden` attribute or an inline `display` (a
 * folded `Accordion` still reads `not.toBeVisible()` without the sheets —
 * `EditCollectionPage.test.jsx` says so), not a class rule. Vitest gives each
 * test file its own document, so nothing leaks into other files. **Use it only
 * where a test asserts behaviour** — not for a check whose point is what the
 * stylesheet does.
 */
export function dropHdsStyles() {
  document.head.querySelectorAll('style').forEach((node) => node.remove());
}

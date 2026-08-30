/**
 * One keyboard tab stop must never contain another.
 *
 * The 2026-08-30 round found 28 places where a router `<Link>` wrapped an HDS
 * `<Button>`: invalid HTML, **two tab stops for one control**, announced
 * "link… button", with the `<a>` taking the focus ring while the `<button>`
 * carried the look. WCAG 4.1.2, and the reason tabbing felt like it landed on
 * nothing.
 *
 * Nothing we had could see it. `jest-axe` returns **no violation** for
 * `<a href><button></a>` (verified, not assumed), and `eslint-plugin-jsx-a11y`
 * has no rule for interactive-inside-interactive at all. So this is a hand-
 * written invariant rather than another rule switched on.
 *
 * It is deliberately about **tab stops**, not about ARIA roles. An element the
 * keyboard never lands on cannot steal a stop from its parent, so HDS's
 * `Linkbox` — whose inner `<a>` is `tabindex="-1"` — is not reported here. That
 * component's defect is its `role="region"`, which is a different failure with
 * a different fix; see the HDS notes in `frontend/CLAUDE.md`.
 */

// What the browser puts in the tab order by default, plus anything opted in.
// `[tabindex="-1"]` is excluded by the guard below, not here, so that an
// element which opts *out* is still recognised as the kind of thing that could
// have opted in.
const CANDIDATE =
  'a[href], button, input, select, textarea, summary, [tabindex], [contenteditable="true"]';

function isTabStop(el) {
  if (el.hasAttribute('disabled') || el.getAttribute('aria-disabled') === 'true') return false;
  if (el.getAttribute('tabindex') === '-1') return false;
  if (el.hidden || el.closest('[hidden], [aria-hidden="true"]')) return false;
  return true;
}

/** The name a reader would hear, trimmed — enough to find the pair in the source. */
function nameOf(el) {
  const label = el.getAttribute('aria-label') || el.textContent || '';
  return label.replace(/\s+/g, ' ').trim().slice(0, 40);
}

function describe(el) {
  const tag = el.tagName.toLowerCase();
  const role = el.getAttribute('role');
  return `${tag}${role ? `[role=${role}]` : ''}`;
}

/**
 * Every tab stop inside `container` that contains another tab stop.
 * Returns `["a › button — “Create collection”", …]`, sorted and de-duplicated, so a
 * failure names the control rather than a DOM node nobody can find.
 */
export function nestedTabStops(container) {
  const found = new Set();
  for (const outer of container.querySelectorAll(CANDIDATE)) {
    if (!isTabStop(outer)) continue;
    for (const inner of outer.querySelectorAll(CANDIDATE)) {
      if (!isTabStop(inner)) continue;
      found.add(`${describe(outer)} › ${describe(inner)} — “${nameOf(outer)}”`);
    }
  }
  return [...found].sort();
}

import { useMemo } from 'react';

/**
 * Theeeme-derived inline styles, centralised from the ~21 pages/components that
 * each re-parsed `theeemeColors` from localStorage and rebuilt the same button
 * style objects on every render.
 *
 * The resting colours are byte-identical to the previous inline versions; the
 * `*-focus` tokens are new (see the comment on them below). The raw localStorage
 * string is read on every
 * render (cheap) but the parse + style objects are memoised on it, so they only
 * recompute when the theeeme actually changes — which still happens (e.g. right
 * after the first login, when HomePage stores the freshly fetched colours).
 *
 * Pass `overrideColors` (e.g. a freshly-fetched `user.theeeme_colors` from the API)
 * to derive the styles from those instead of localStorage — used where the
 * authoritative colours are already in hand and localStorage may lag. A nullish or
 * empty override falls back to localStorage, then to DEFAULT_COLORS.
 *
 * Returns:
 * - `tc`: the raw theeeme colour map (`color_01`..`color_06`, HDS token names).
 * - `koro`: the user's Koros wave type (default `'basic'`).
 * - `btnStyle`: primary button (theeeme `color_01` background, `color_06` text).
 * - `btnSecondaryStyle`: secondary button (white background, `color_01` border, `color_04` text).
 *
 * Both button styles pin the `*-focus` tokens to the resting colours, so keyboard
 * focus never recolours the button — the two-tone ring in `App.css` marks it.
 *
 * - `uploadStyle`: the `--upload-*` CSS vars for the ImageUpload/GalleryUpload wrapper.
 */
// Fallback palette for a viewer with no stored theeeme yet — e.g. an anonymous
// visitor on a PUBLIC collection, or anyone before their first login. Without it
// `tc` is `{}`, so `--hero-text-color` stays unset and the hero title falls back
// to black-90 — invisible on the dark hero. It's a real, coherent theeeme row
// (the "M&V" palette, code 5BC8W6: black hero + white text + summer/yellow
// accents) rather than a hand-mixed set of tokens, so every surface matches.
export const DEFAULT_COLORS = {
  color_01: 'summer',
  color_02: 'black-5',
  color_03: 'black',
  color_04: 'black',
  color_05: 'white',
  color_06: 'black',
};

export default function useTheeeme(overrideColors) {
  const raw = localStorage.getItem('theeemeColors') || '{}';
  const koro = localStorage.getItem('koro') || 'basic';
  // Stringify the override for a stable memo dependency (a caller may pass a fresh
  // object reference each render, e.g. `user?.theeeme_colors`).
  const overrideKey =
    overrideColors && Object.keys(overrideColors).length > 0 ? JSON.stringify(overrideColors) : '';

  return useMemo(() => {
    let tc;
    if (overrideKey) {
      tc = JSON.parse(overrideKey);
    } else {
      let parsed;
      try {
        parsed = JSON.parse(raw);
      } catch {
        parsed = null;
      }
      tc = parsed && Object.keys(parsed).length > 0 ? parsed : DEFAULT_COLORS;
    }
    // The `*-focus` tokens repeat the resting colours on purpose. HDS repaints a
    // button when it takes focus — the `primary` variant declares
    // `--background-color-focus: var(--color-bus)` and `secondary` declares it
    // `transparent` — and those declarations WIN over the `--background-color`
    // passed here, because HDS's fallback chain
    // (`var(--background-color-focus, var(--computed-background-color, …))`)
    // only reaches our value when nobody declares the focus one. On a
    // suomenlinna theeeme that turned a pink button blue with black text
    // (1.75:1, WCAG 1.4.3 asks 4.5:1) exactly when the keyboard arrived at it.
    // So the focus state must recolour nothing: what marks focus is the
    // two-tone ring in App.css, not a change of fill.
    const primaryColor = tc.color_06 ? `var(--color-${tc.color_06})` : 'var(--color-white)';
    const secondaryColor = tc.color_04 ? `var(--color-${tc.color_04})` : undefined;
    // Outer band of that ring. HDS draws the button's own outline with a
    // higher-specificity rule, so its colour has to arrive as a token; the
    // inner white band and the gap between them come from App.css, which HDS
    // does not contest.
    const focusOutline = 'var(--color-black)';
    const btnStyle = tc.color_01
      ? {
          '--background-color': `var(--color-${tc.color_01})`,
          '--background-color-hover': `var(--color-${tc.color_01}-dark)`,
          '--color': primaryColor,
          '--border-color': `var(--color-${tc.color_01})`,
          '--background-color-focus': `var(--color-${tc.color_01})`,
          '--border-color-focus': `var(--color-${tc.color_01})`,
          '--color-focus': primaryColor,
          '--outline-color-focus': focusOutline,
        }
      : undefined;
    const btnSecondaryStyle = tc.color_01
      ? {
          '--background-color': 'var(--color-white)',
          '--border-color': `var(--color-${tc.color_01})`,
          '--color': secondaryColor,
          '--background-color-hover': `var(--color-${tc.color_01})`,
          '--color-hover': tc.color_06 ? `var(--color-${tc.color_06})` : 'var(--color-white)',
          '--background-color-focus': 'var(--color-white)',
          '--border-color-focus': `var(--color-${tc.color_01})`,
          '--color-focus': secondaryColor,
          '--outline-color-focus': focusOutline,
        }
      : undefined;
    const uploadStyle = tc.color_01
      ? {
          '--upload-border': `var(--color-${tc.color_01})`,
          '--upload-color': tc.color_04
            ? `var(--color-${tc.color_04})`
            : `var(--color-${tc.color_01})`,
          '--upload-bg-hover': `var(--color-${tc.color_01})`,
          '--upload-color-hover': tc.color_06
            ? `var(--color-${tc.color_06})`
            : 'var(--color-white)',
        }
      : {};
    return { tc, koro, btnStyle, btnSecondaryStyle, uploadStyle };
  }, [raw, koro, overrideKey]);
}

import { readFileSync } from 'node:fs';
import { renderHook } from '@testing-library/react';
import { describe, test, expect } from 'vitest';
import useTheeeme from '../hooks/useTheeeme';

// jsdom can't run axe's colour-contrast rule (it needs real layout/paint), so we
// verify the curated theeeme palette here instead: for every theeeme, the text
// roles that sit on a coloured background must meet WCAG 2.1 AA (>= 4.5:1 for
// normal text).
//
// The 12 palettes mirror the backend seed (core/migrations/0036, as amended by
// 0081 color_02 -> -medium-light and 0112 Vaakuna color_05 -> black). Keep this
// list in lockstep with that seed.
const THEEEMES = [
  {
    name: 'Bussi',
    color_01: 'bus',
    color_02: 'suomenlinna-medium-light',
    color_03: 'copper',
    color_04: 'black',
    color_05: 'black',
    color_06: 'white',
  },
  {
    name: 'Engel',
    color_01: 'engel',
    color_02: 'bus-medium-light',
    color_03: 'copper',
    color_04: 'black',
    color_05: 'black',
    color_06: 'black',
  },
  {
    name: 'Hopea',
    color_01: 'gold',
    color_02: 'bus-medium-light',
    color_03: 'silver',
    color_04: 'black',
    color_05: 'black',
    color_06: 'black',
  },
  {
    name: 'Kesä',
    color_01: 'summer',
    color_02: 'engel-medium-light',
    color_03: 'tram',
    color_04: 'black',
    color_05: 'white',
    color_06: 'black',
  },
  {
    name: 'Kupari',
    color_01: 'copper',
    color_02: 'fog-medium-light',
    color_03: 'suomenlinna',
    color_04: 'black',
    color_05: 'black',
    color_06: 'black',
  },
  {
    name: 'Kulta',
    color_01: 'gold',
    color_02: 'fog-medium-light',
    color_03: 'metro',
    color_04: 'black',
    color_05: 'black',
    color_06: 'black',
  },
  {
    name: 'Metro',
    color_01: 'metro',
    color_02: 'suomenlinna-medium-light',
    color_03: 'gold',
    color_04: 'black',
    color_05: 'black',
    color_06: 'black',
  },
  {
    name: 'Sumu',
    color_01: 'fog',
    color_02: 'engel-medium-light',
    color_03: 'metro',
    color_04: 'black',
    color_05: 'black',
    color_06: 'black',
  },
  {
    name: 'Spåra',
    color_01: 'tram',
    color_02: 'engel-medium-light',
    color_03: 'summer',
    color_04: 'black',
    color_05: 'black',
    color_06: 'white',
  },
  {
    name: 'Suomenlinna',
    color_01: 'suomenlinna',
    color_02: 'bus-medium-light',
    color_03: 'bus',
    color_04: 'black',
    color_05: 'white',
    color_06: 'black',
  },
  {
    name: 'Vaakuna',
    color_01: 'summer',
    color_02: 'fog-medium-light',
    color_03: 'suomenlinna',
    color_04: 'black',
    color_05: 'black',
    color_06: 'black',
  },
  {
    name: 'M&V',
    color_01: 'summer',
    color_02: 'black-5',
    color_03: 'black',
    color_04: 'black',
    color_05: 'white',
    color_06: 'black',
  },
];

// The role pairings that render text on a coloured surface (frontend/CLAUDE.md
// "Theeeme Color Roles"): body text, primary-button label, koros/hero text.
const PAIRINGS = [
  { role: 'body text (color_04 on color_02)', fg: 'color_04', bg: 'color_02' },
  { role: 'primary button (color_06 on color_01)', fg: 'color_06', bg: 'color_01' },
  { role: 'koros/hero text (color_05 on color_03)', fg: 'color_05', bg: 'color_03' },
];

const AA_NORMAL = 4.5;

// Resolve HDS colour tokens to hex from the design-tokens package — the single
// source of truth for the values behind names like "bus" or "fog-medium-light".
function loadTokenHexMap() {
  const css = readFileSync('node_modules/hds-design-tokens/lib/color/all.css', 'utf8');
  const map = { black: '#000000', white: '#ffffff' };
  for (const m of css.matchAll(/--color-([a-z0-9-]+):\s*(#[0-9a-fA-F]{3,8})/g)) {
    map[m[1]] = m[2];
  }
  return map;
}

function relativeLuminance(hex) {
  const h = hex.replace('#', '');
  const chan = (i) => {
    const c = parseInt(h.slice(i, i + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * chan(0) + 0.7152 * chan(2) + 0.0722 * chan(4);
}

function contrastRatio(a, b) {
  const la = relativeLuminance(a);
  const lb = relativeLuminance(b);
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
}

describe('theeeme palette WCAG AA contrast', () => {
  const tokens = loadTokenHexMap();

  test('all curated theeeme role tokens resolve to a hex value', () => {
    for (const theeeme of THEEEMES) {
      for (const key of ['color_01', 'color_02', 'color_03', 'color_04', 'color_05', 'color_06']) {
        expect(tokens[theeeme[key]], `${theeeme.name} ${key}=${theeeme[key]}`).toMatch(
          /^#[0-9a-fA-F]{6}$/
        );
      }
    }
  });

  test.each(THEEEMES)('$name meets AA for every text-on-colour role', (theeeme) => {
    for (const { role, fg, bg } of PAIRINGS) {
      const ratio = contrastRatio(tokens[theeeme[fg]], tokens[theeeme[bg]]);
      expect(ratio, `${theeeme.name} — ${role}: ${ratio.toFixed(2)}:1`).toBeGreaterThanOrEqual(
        AA_NORMAL
      );
    }
  });
});

// ── Keyboard focus ─────────────────────────────────────────────────────
// Two separate promises, so two separate suites.
//
// The first is that focus never RECOLOURS a button. HDS's variant classes
// declare `--background-color-focus` themselves (`primary` → `--color-bus`,
// `secondary` → transparent) and those beat the resting colour we pass, so a
// suomenlinna theeeme used to turn its pink button blue under black text —
// 1.75:1, and only while the keyboard was on it, which is the one moment it had
// to be readable. `useTheeeme` now pins the `*-focus` tokens to the resting
// ones; this asserts that, rather than the CSS, because the hook is where a
// future edit would drop them.
//
// The second is that the ring itself stays visible. It is read OUT of the
// source — the outline colour from App.css, the HDS-button one from
// useTheeeme.js — so replacing the two-tone ring with any single colour turns
// this red instead of leaving a test that merely restates a constant.

const AA_NON_TEXT = 3; // WCAG 1.4.11

// Every colour a theeeme can put directly under the ring.
const RING_SURFACES = [
  { role: 'primary button fill', token: (t) => t.color_01 },
  { role: 'secondary button fill', token: () => 'white' },
  { role: 'hero', token: (t) => t.color_03 },
  { role: 'page background', token: (t) => t.color_02 },
];

// `var(--color-foo)` → `foo`, so a hex can be looked up for it.
function tokenNameFrom(cssValue, what) {
  const m = /var\(--color-([a-z0-9-]+)\)/.exec(cssValue);
  if (!m) throw new Error(`${what} is not a --color-* token: ${cssValue}`);
  return m[1];
}

function ringBands() {
  const css = readFileSync('src/App.css', 'utf8');
  const block = /:focus-visible\s*\{([^}]*)\}/.exec(css);
  if (!block) throw new Error('no bare :focus-visible rule in App.css');
  const outline = /outline:\s*\d+px\s+solid\s+([^;]+);/.exec(block[1]);
  const shadow = /box-shadow:\s*0 0 0 \d+px\s+([^;]+);/.exec(block[1]);
  if (!outline || !shadow) {
    throw new Error('the :focus-visible ring lost one of its two bands');
  }
  const hook = readFileSync('src/hooks/useTheeeme.js', 'utf8');
  const hdsOutline = /const focusOutline = '([^']+)';/.exec(hook);
  if (!hdsOutline) throw new Error('useTheeeme no longer names an HDS focus outline');
  return {
    outer: tokenNameFrom(outline[1].trim(), 'the outer band'),
    inner: tokenNameFrom(shadow[1].trim(), 'the inner band'),
    hdsOuter: tokenNameFrom(hdsOutline[1], "the HDS buttons' outline"),
  };
}

describe('keyboard focus ring', () => {
  const tokens = loadTokenHexMap();
  const bands = ringBands();

  test('HDS buttons get the same outer band as everything else', () => {
    expect(bands.hdsOuter).toBe(bands.outer);
  });

  test('the two bands are told apart from each other', () => {
    const ratio = contrastRatio(tokens[bands.inner], tokens[bands.outer]);
    expect(ratio, `${bands.inner} vs ${bands.outer}: ${ratio.toFixed(2)}:1`).toBeGreaterThanOrEqual(
      AA_NON_TEXT
    );
  });

  test.each(THEEEMES)('$name — one band stays visible on every surface', (theeeme) => {
    for (const { role, token } of RING_SURFACES) {
      const surface = tokens[token(theeeme)];
      const best = Math.max(
        contrastRatio(tokens[bands.inner], surface),
        contrastRatio(tokens[bands.outer], surface)
      );
      expect(
        best,
        `${theeeme.name} — ring on ${role} (${token(theeeme)}): best band ${best.toFixed(2)}:1`
      ).toBeGreaterThanOrEqual(AA_NON_TEXT);
    }
  });
});

describe('focus never recolours a button', () => {
  // A real theeeme whose colours differ from what HDS forces on focus, so a
  // regression shows up as a wrong value rather than a coincidence.
  const SUOMENLINNA = THEEEMES.find((t) => t.name === 'Suomenlinna');

  test.each([
    ['primary', 'btnStyle'],
    ['secondary', 'btnSecondaryStyle'],
  ])('%s keeps its resting colours under focus', (_label, key) => {
    const { result } = renderHook(() => useTheeeme(SUOMENLINNA));
    const style = result.current[key];
    expect(style['--background-color-focus']).toBe(style['--background-color']);
    expect(style['--border-color-focus']).toBe(style['--border-color']);
    expect(style['--color-focus']).toBe(style['--color']);
  });
});

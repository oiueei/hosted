import { describe, test, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import {
  DETAIL_TYPES,
  KIND_THING_TYPES,
  TAG_THEMES,
  deriveThingType,
  kindOfThingType,
} from './things';
import parity from '../test/kindVerbParity.json';

// The table lives in src/test/kindVerbParity.json, read by this suite and by
// core/tests/unit/test_kind_verb_parity.py (one of the shared fixtures CLAUDE.md
// names): the form's copy of the server's rule and the rule itself stay one.
describe('the form and the server agree on the verb a price makes', () => {
  test('the kinds hold exactly the verbs the server says', () => {
    expect(KIND_THING_TYPES).toEqual(parity.kinds);
  });

  test.each(parity.cases.map((c) => [c.kind, c.fee, c.verb, c.note]))(
    '%s with a price of %s is %s (%s)',
    (kind, fee, verb) => {
      expect(deriveThingType(kind, fee)).toBe(verb);
    }
  );
});

describe('the verb a thing takes follows its collection’s kind and its price', () => {
  test.each([
    ['STALL', '', 'GIFT_THING'],
    ['STALL', undefined, 'GIFT_THING'],
    ['STALL', null, 'GIFT_THING'],
    ['STALL', 0, 'GIFT_THING'],
    ['STALL', '0', 'GIFT_THING'],
    ['STALL', '0.00', 'GIFT_THING'],
    ['STALL', 5, 'SELL_THING'],
    ['STALL', '4.50', 'SELL_THING'],
    ['LIBRARY', '', 'LEND_THING'],
    ['LIBRARY', 0, 'LEND_THING'],
    ['LIBRARY', 3, 'RENT_THING'],
    ['LIBRARY', '0.01', 'RENT_THING'],
    ['SHED', '', 'RESERVE_THING'],
    ['SHED', 12, 'RESERVE_THING'],
  ])('%s with a price of %j is %s', (kind, fee, expected) => {
    expect(deriveThingType(kind, fee)).toBe(expected);
  });

  test('a kind it does not know is read as a stall', () => {
    expect(deriveThingType('', 5)).toBe('SELL_THING');
  });
});

describe('every verb belongs to one kind', () => {
  test.each(
    Object.entries(KIND_THING_TYPES).flatMap(([kind, verbs]) => verbs.map((v) => [v, kind]))
  )('%s is a %s verb', (verb, kind) => {
    expect(kindOfThingType(verb)).toBe(kind);
  });

  test('and an unknown one belongs to none', () => {
    expect(kindOfThingType('WISH_THING')).toBeUndefined();
  });
});

test('a rental has a condition and a place, like a loan', () => {
  expect(DETAIL_TYPES).toContain('RENT_THING');
});

// jsdom cannot run axe's colour-contrast rule, so the tag themes are checked here:
// every tag's text must meet WCAG AA (4.5:1) on its own background, whether the
// colour is a hex or an HDS token resolved from the design-tokens package.
describe('status tag themes meet WCAG AA contrast', () => {
  const css = readFileSync('node_modules/hds-design-tokens/lib/color/all.css', 'utf8');
  const tokens = { black: '#000000', white: '#ffffff' };
  for (const m of css.matchAll(/--color-([a-z0-9-]+):\s*(#[0-9a-fA-F]{3,8})/g)) tokens[m[1]] = m[2];

  const hexOf = (value) => {
    const token = /^var\(--color-([a-z0-9-]+)\)$/.exec(value);
    return token ? tokens[token[1]] : value;
  };
  const luminance = (hex) => {
    const channel = (i) => {
      const c = parseInt(hex.slice(i, i + 2), 16) / 255;
      return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
    };
    return 0.2126 * channel(1) + 0.7152 * channel(3) + 0.0722 * channel(5);
  };
  const ratio = (a, b) => {
    const [x, y] = [luminance(a), luminance(b)];
    return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05);
  };

  test.each(Object.entries(TAG_THEMES))('%s', (name, theme) => {
    const fg = hexOf(theme['--tag-color']);
    const bg = hexOf(theme['--tag-background']);
    expect(fg, `${name} text colour resolves`).toMatch(/^#[0-9a-f]{6}$/i);
    expect(bg, `${name} background resolves`).toMatch(/^#[0-9a-f]{6}$/i);
    expect(ratio(fg, bg)).toBeGreaterThanOrEqual(4.5);
  });
});

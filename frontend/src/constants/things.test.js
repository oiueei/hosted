import { describe, test, expect } from 'vitest';
import { DETAIL_TYPES, KIND_THING_TYPES, deriveThingType, kindOfThingType } from './things';
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

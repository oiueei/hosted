import { describe, test, expect } from 'vitest';
import { markMixedVerbs } from './bookingRows';

const row = (_type, over = {}) => ({ _id: `${_type}-${Math.random()}`, _type, ...over });

describe('markMixedVerbs', () => {
  test('rows of one verb are all marked as not showing it', () => {
    const rows = markMixedVerbs([row('RENT_THING'), row('RENT_THING'), row('RENT_THING')]);

    expect(rows.map((r) => r._showType)).toEqual([false, false, false]);
  });

  test('rows that mix verbs are all marked as showing it', () => {
    const rows = markMixedVerbs([row('RENT_THING'), row('RENT_THING'), row('RESERVE_THING')]);

    expect(rows.map((r) => r._showType)).toEqual([true, true, true]);
  });

  test('a single row, and no rows, are not a mix', () => {
    expect(markMixedVerbs([row('LEND_THING')]).map((r) => r._showType)).toEqual([false]);
    expect(markMixedVerbs([])).toEqual([]);
  });

  test('it keeps the rest of every row and does not touch the ones it was given', () => {
    const original = [row('RENT_THING', { _code: 'A' }), row('GIFT_THING', { _code: 'B' })];
    const marked = markMixedVerbs(original);

    expect(marked.map((r) => r._code)).toEqual(['A', 'B']);
    expect(original.every((r) => !('_showType' in r))).toBe(true);
  });
});

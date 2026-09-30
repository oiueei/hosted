import { describe, test, expect } from 'vitest';
import parity from '../test/nextPathParity.json';
import { safeNextPath, loginPathFor } from './nextPath';

// The tables live in src/test/nextPathParity.json, read by this suite and by
// core/tests/unit/test_safe_next_path.py (one of the two shared fixtures
// CLAUDE.md names): the server is the gate, this is defence in depth, and one
// file is what stops them drifting. The one row JSON cannot carry stays local:
// `undefined` has no JSON spelling, and "a non-string is refused" is worth
// saying on this side too.
const ACCEPTED = parity.accepted;
const REJECTED = [...parity.rejected, undefined];

describe('safeNextPath', () => {
  test.each(ACCEPTED)('a same-site path the SPA has is returned untouched: %s', (value) => {
    expect(safeNextPath(value)).toBe(value);
  });

  test.each(REJECTED.map((v) => [JSON.stringify(v), v]))(
    'anything that could leave the site or loop is dropped: %s',
    (_label, value) => {
      expect(safeNextPath(value)).toBe('');
    }
  );

  test('the shared table travelled intact', () => {
    // The file held 31 rejected rows (+ undefined, which JSON cannot carry)
    // and 8 accepted when the tables moved into it. The floor is against a
    // reshaped or emptied copy silently testing nothing.
    expect(parity.rejected.length).toBeGreaterThanOrEqual(30);
    expect(ACCEPTED.length).toBeGreaterThanOrEqual(8);
    // The boundary rows travel as full strings; a hand edit that changed their
    // length would quietly move the limit every other row is measured against.
    expect(ACCEPTED.at(-1), 'exactly at the limit').toHaveLength(256);
    expect(parity.rejected.at(-1), 'one character over the limit').toHaveLength(257);
  });

  test('a lone percent sign does not throw (the server tolerates it, so must this)', () => {
    // decodeURIComponent('%') throws; the whitelist allows '%', so a naive port of
    // the rule would crash on a value the server accepts.
    expect(() => safeNextPath('/a%')).not.toThrow();
    expect(safeNextPath('/a%')).toBe('/a%');
  });
});

describe('loginPathFor', () => {
  test('remembers where the reader was, path and query, encoded into one parameter', () => {
    expect(loginPathFor({ pathname: '/collections/X/things/Y', search: '?z=1' })).toBe(
      '/login?next=%2Fcollections%2FX%2Fthings%2FY%3Fz%3D1'
    );
  });

  test('is a plain /login when there is nowhere to come back to', () => {
    expect(loginPathFor({ pathname: '/', search: '' })).toBe('/login');
    expect(loginPathFor({ pathname: '/login', search: '?next=%2Fme' })).toBe('/login');
    expect(loginPathFor({})).toBe('/login');
    expect(loginPathFor()).toBe('/login');
  });
});

import { describe, test, expect } from 'vitest';
import { safeNextPath, loginPathFor } from './nextPath';

// The same tables as core/tests/unit/test_safe_next_path.py (the rule is
// duplicated on purpose: the server is the gate, this is defence in depth, and
// nothing but these two tables stops them drifting). Where a row has no
// meaning in JS it is left out: there is no `\n`-before-`$` quirk to guard, since
// a JS `$` without the `m` flag only matches at the very end — but the row stays,
// because "a trailing newline is refused" is the behaviour either way.
const ACCEPTED = [
  '/collections/AbC123/things/XyZ789',
  '/collections/new',
  '/me/edit',
  '/my-bookings',
  '/AbC123',
  '/collections/AbC123/join?thing=XyZ789',
  '/collections/AbC123/things/XyZ789?back=%2Fcollections%2FAbC123',
  `/x${'a'.repeat(254)}`, // exactly 256 characters
];

const REJECTED = [
  '//evil.com',
  '/\\evil.com',
  'https://evil.com',
  'javascript:alert(1)',
  '/login',
  '/login?next=/x',
  '/login/',
  '/LOGIN',
  '/%6Cogin',
  '/logout',
  '/verify/tok',
  '/rsvp/tok',
  '/magic-link/tok',
  '/',
  '/?a=1',
  '',
  null,
  undefined,
  123,
  ['/me'],
  { path: '/me' },
  '/a b',
  '/a\nb',
  '/me\n',
  '/x#y',
  '/a:b',
  '/a<b',
  '/../me',
  '/me/..',
  '/%2e%2e/me',
  '/%2E%2E/me',
  `/x${'a'.repeat(255)}`, // one character over the limit
];

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

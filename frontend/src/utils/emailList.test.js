import { describe, test, expect } from 'vitest';
import { parseEmailList } from './emailList';

describe('parseEmailList', () => {
  test('one address is a list of one', () => {
    expect(parseEmailList('lalo@oiueei.com')).toEqual(['lalo@oiueei.com']);
  });

  test('commas separate, and the spaces around an address go away', () => {
    expect(parseEmailList('lalo@oiueei.com, lelo@oiueei.com')).toEqual([
      'lalo@oiueei.com',
      'lelo@oiueei.com',
    ]);
    expect(parseEmailList('  lalo@oiueei.com ,lelo@oiueei.com  ,  lili@oiueei.com ')).toEqual([
      'lalo@oiueei.com',
      'lelo@oiueei.com',
      'lili@oiueei.com',
    ]);
  });

  test('a semicolon separates too', () => {
    expect(parseEmailList('a@x.com;b@y.com; c@z.com')).toEqual(['a@x.com', 'b@y.com', 'c@z.com']);
  });

  test('line breaks separate — a column of addresses pasted as it is', () => {
    expect(parseEmailList('a@x.com\nb@y.com\r\nc@z.com\n')).toEqual([
      'a@x.com',
      'b@y.com',
      'c@z.com',
    ]);
  });

  test('so do plain spaces and tabs, which is what a browser makes of those line breaks in a one-line field', () => {
    expect(parseEmailList('a@x.com b@y.com\tc@z.com')).toEqual(['a@x.com', 'b@y.com', 'c@z.com']);
  });

  test('the separators can be mixed', () => {
    expect(parseEmailList('a@x.com, b@y.com;\n c@z.com d@w.com')).toEqual([
      'a@x.com',
      'b@y.com',
      'c@z.com',
      'd@w.com',
    ]);
  });

  test('an address repeated counts once, in any case, the first spelling kept and the order too', () => {
    expect(
      parseEmailList('Lalo@Oiueei.com, lelo@oiueei.com, lalo@oiueei.com, LELO@OIUEEI.COM')
    ).toEqual(['Lalo@Oiueei.com', 'lelo@oiueei.com']);
  });

  test('nothing between two separators is nothing: no empty addresses', () => {
    expect(parseEmailList(',, a@x.com ,; , b@y.com,')).toEqual(['a@x.com', 'b@y.com']);
  });

  test.each([[''], ['   '], [' , ; '], ['\n\n'], [null], [undefined]])(
    'nothing to invite in %j: an empty list',
    (text) => {
      expect(parseEmailList(text)).toEqual([]);
    }
  );

  test('it does not decide what is an address: that is the server’s', () => {
    expect(parseEmailList('not-an-email, @, a@b')).toEqual(['not-an-email', '@', 'a@b']);
  });
});

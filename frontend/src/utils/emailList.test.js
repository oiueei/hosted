import { describe, test, expect } from 'vitest';
import { parseEmailList } from './emailList';

describe('parseEmailList', () => {
  test('one address is a list of one', () => {
    expect(parseEmailList('lala@your-domain.test')).toEqual(['lala@your-domain.test']);
  });

  test('commas separate, and the spaces around an address go away', () => {
    expect(parseEmailList('lala@your-domain.test, lele@your-domain.test')).toEqual([
      'lala@your-domain.test',
      'lele@your-domain.test',
    ]);
    expect(
      parseEmailList('  lala@your-domain.test ,lele@your-domain.test  ,  lili@your-domain.test ')
    ).toEqual(['lala@your-domain.test', 'lele@your-domain.test', 'lili@your-domain.test']);
  });

  test('a semicolon separates too', () => {
    expect(
      parseEmailList('lala1@your-domain.test;lele1@your-domain.test; lili1@your-domain.test')
    ).toEqual(['lala1@your-domain.test', 'lele1@your-domain.test', 'lili1@your-domain.test']);
  });

  test('line breaks separate — a column of addresses pasted as it is', () => {
    expect(
      parseEmailList('lala1@your-domain.test\nlele1@your-domain.test\r\nlili1@your-domain.test\n')
    ).toEqual(['lala1@your-domain.test', 'lele1@your-domain.test', 'lili1@your-domain.test']);
  });

  test('so do plain spaces and tabs, which is what a browser makes of those line breaks in a one-line field', () => {
    expect(
      parseEmailList('lala1@your-domain.test lele1@your-domain.test\tlili1@your-domain.test')
    ).toEqual(['lala1@your-domain.test', 'lele1@your-domain.test', 'lili1@your-domain.test']);
  });

  test('the separators can be mixed', () => {
    expect(
      parseEmailList(
        'lala1@your-domain.test, lele1@your-domain.test;\n lili1@your-domain.test lolo@your-domain.test'
      )
    ).toEqual([
      'lala1@your-domain.test',
      'lele1@your-domain.test',
      'lili1@your-domain.test',
      'lolo@your-domain.test',
    ]);
  });

  test('an address repeated counts once, in any case, the first spelling kept and the order too', () => {
    expect(
      parseEmailList(
        'Lala@Your-Domain.TEST, lele@your-domain.test, lala@your-domain.test, LELE@Your-Domain.TEST'
      )
    ).toEqual(['Lala@Your-Domain.TEST', 'lele@your-domain.test']);
  });

  test('nothing between two separators is nothing: no empty addresses', () => {
    expect(parseEmailList(',, lala1@your-domain.test ,; , lele1@your-domain.test,')).toEqual([
      'lala1@your-domain.test',
      'lele1@your-domain.test',
    ]);
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

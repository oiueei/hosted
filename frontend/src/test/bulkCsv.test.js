import { describe, test, expect } from 'vitest';
import Papa from 'papaparse';
import { mapRow, photoNames, validateRows, MAX_GALLERY, MAX_ROWS } from '../utils/bulkCsv';
import { CSV_PARSE_OPTIONS } from '../utils/csv';

describe('mapRow', () => {
  test('keeps known columns, trims them, and drops empty/whitespace cells', () => {
    const row = mapRow(
      { headline: '  Cazo  ', type: 'RENT_THING', fee: '5', description: '   ', location: 'BCN' },
      false
    );
    expect(row).toEqual({ headline: 'Cazo', type: 'RENT_THING', fee: '5', location: 'BCN' });
    expect(row).not.toHaveProperty('description'); // whitespace-only → dropped
  });

  test('ignores unknown columns', () => {
    const row = mapRow({ headline: 'X', evil: 'drop me', sku: '123' }, false);
    expect(row).toEqual({ headline: 'X' });
  });

  test('splits the tags cell on the pipe, trims and drops blanks', () => {
    const row = mapRow({ headline: 'X', tags: ' Cocina | Vintage |  | Metal ' }, false);
    expect(row.tags).toEqual(['Cocina', 'Vintage', 'Metal']);
  });

  test('omits tags when the cell is empty or whitespace', () => {
    expect(mapRow({ headline: 'X', tags: '   ' }, false)).not.toHaveProperty('tags');
    expect(mapRow({ headline: 'X' }, false)).not.toHaveProperty('tags');
  });

  test('keeps photo only when withPhoto is true (ZIP path)', () => {
    expect(mapRow({ headline: 'X', photo: 'cazo.jpg' }, true)).toMatchObject({ photo: 'cazo.jpg' });
    expect(mapRow({ headline: 'X', photo: 'cazo.jpg' }, false)).not.toHaveProperty('photo');
  });
});

describe('mapRow — deposit', () => {
  test('keeps the deposit column, trimmed, like every other scalar column', () => {
    const row = mapRow({ headline: 'X', type: 'LEND_THING', deposit: ' 50 ' }, false);
    expect(row.deposit).toBe('50');
  });

  test('omits deposit when the cell is empty or whitespace, so it never overwrites a default', () => {
    expect(mapRow({ headline: 'X', deposit: '   ' }, false)).not.toHaveProperty('deposit');
    expect(mapRow({ headline: 'X' }, false)).not.toHaveProperty('deposit');
  });

  test('a locale decimal comma passes through untouched — the server, not this layer, normalises it', () => {
    // LocaleDecimalField (backend) accepts "50,00"; this mapping step only
    // trims whitespace, the same as it does for fee.
    expect(mapRow({ headline: 'X', deposit: '50,00' }, false).deposit).toBe('50,00');
  });

  test('a row with no deposit column at all is unaffected — an existing CSV keeps working', () => {
    // The whole point of appending the column at the end rather than the
    // middle: a file with no `deposit` header simply never sets `raw.deposit`.
    const row = mapRow({ headline: 'X', type: 'GIFT_THING', fee: undefined }, false);
    expect(row).not.toHaveProperty('deposit');
  });
});

describe('validateRows', () => {
  const rowsOf = (n, withHeadline = true) =>
    Array.from({ length: n }, (_, i) =>
      withHeadline ? { headline: `h${i}` } : { type: 'GIFT_THING' }
    );

  test('flags an empty set', () => {
    expect(validateRows([])).toBe('empty');
  });

  test('flags more than the max row count', () => {
    expect(validateRows(rowsOf(MAX_ROWS + 1))).toBe('tooMany');
  });

  test('accepts exactly the max row count', () => {
    expect(validateRows(rowsOf(MAX_ROWS))).toBeNull();
  });

  test('flags any row missing a headline', () => {
    expect(validateRows([{ headline: 'ok' }, { type: 'GIFT_THING' }])).toBe('headlineRequired');
  });

  test('passes when every row has a headline and bounds hold', () => {
    expect(validateRows(rowsOf(3))).toBeNull();
  });
});

describe('CSV_PARSE_OPTIONS', () => {
  // Regression: a Spanish-Excel CSV ("sep=;" hint + ";") parsed
  // fine as a plain .csv but broke inside a .zip, where the string path skipped
  // delimitersToGuess + stripSepLine. The shared options serve both paths.
  test('strips the sep=; line and auto-detects ";" on a string (the ZIP path)', () => {
    const text = 'sep=;\nheadline;type;fee\nCazo de acero;RENT_THING;1\nSartén;SELL_THING;3';
    let captured;
    Papa.parse(text, {
      ...CSV_PARSE_OPTIONS,
      complete: (result) => {
        captured = result;
      },
    });
    expect(captured.meta.delimiter).toBe(';');
    expect(captured.meta.fields).toEqual(['headline', 'type', 'fee']);
    expect(captured.data).toEqual([
      { headline: 'Cazo de acero', type: 'RENT_THING', fee: '1' },
      { headline: 'Sartén', type: 'SELL_THING', fee: '3' },
    ]);
  });

  test('still auto-detects "," and lower-cases headers when there is no sep line', () => {
    const text = 'Headline,Type\nCazo,GIFT_THING';
    let captured;
    Papa.parse(text, {
      ...CSV_PARSE_OPTIONS,
      complete: (result) => {
        captured = result;
      },
    });
    expect(captured.meta.delimiter).toBe(',');
    expect(captured.meta.fields).toEqual(['headline', 'type']);
    expect(captured.data).toEqual([{ headline: 'Cazo', type: 'GIFT_THING' }]);
  });
});

describe('photoNames', () => {
  test('lists each distinct filename once, in the order it first appears', () => {
    const rows = [
      { headline: 'A', photo: 'b.jpg' },
      { headline: 'B', photo: 'a.jpg' },
      { headline: 'C', photo: 'b.jpg' },
    ];
    expect(photoNames(rows)).toEqual(['b.jpg', 'a.jpg']);
  });

  test('skips the rows that name no photo', () => {
    const rows = [{ headline: 'A' }, { headline: 'B', photo: 'a.jpg' }, { headline: 'C' }];
    expect(photoNames(rows)).toEqual(['a.jpg']);
  });

  test('is empty when no row names one', () => {
    expect(photoNames([{ headline: 'A' }])).toEqual([]);
    expect(photoNames([])).toEqual([]);
  });
});

describe('mapRow — the carousel (photos)', () => {
  test('splits the photos cell on the pipe, trims and drops blanks', () => {
    const row = mapRow({ headline: 'X', photos: 'a.jpg | b.jpg|' }, true);
    expect(row.photos).toEqual(['a.jpg', 'b.jpg']);
  });

  test('keeps the order the cell lists them in', () => {
    expect(mapRow({ headline: 'X', photos: 'c.jpg|a.jpg|b.jpg' }, true).photos).toEqual([
      'c.jpg',
      'a.jpg',
      'b.jpg',
    ]);
  });

  test('omits photos when the cell is empty or only pipes and spaces', () => {
    expect(mapRow({ headline: 'X', photos: '   ' }, true)).not.toHaveProperty('photos');
    expect(mapRow({ headline: 'X', photos: ' | | ' }, true)).not.toHaveProperty('photos');
    expect(mapRow({ headline: 'X' }, true)).not.toHaveProperty('photos');
  });

  test('is read only for a ZIP, as photo is: a plain CSV ignores it', () => {
    expect(mapRow({ headline: 'X', photos: 'a.jpg|b.jpg' }, false)).not.toHaveProperty('photos');
  });
});

describe('validateRows — the carousel', () => {
  const rowWith = (count) => ({
    headline: 'X',
    photos: Array.from({ length: count }, (_, i) => `p${i}.jpg`),
  });

  test('a thing takes at most 8 extra photos', () => {
    expect(MAX_GALLERY).toBe(8);
    expect(validateRows([rowWith(8)])).toBeNull();
    expect(validateRows([rowWith(9)])).toBe('galleryTooLong');
  });

  test('one row over the limit refuses the whole file', () => {
    expect(validateRows([rowWith(1), rowWith(9), rowWith(2)])).toBe('galleryTooLong');
  });

  test('a row with no carousel is not affected', () => {
    expect(validateRows([{ headline: 'X' }])).toBeNull();
  });
});

describe('photoNames — covers and carousels together', () => {
  test('lists the cover and then the carousel of each row, in the order they first appear', () => {
    const rows = [
      { headline: 'A', photo: 'cover-a.jpg', photos: ['x.jpg', 'y.jpg'] },
      { headline: 'B', photo: 'cover-b.jpg', photos: ['z.jpg'] },
    ];
    expect(photoNames(rows)).toEqual(['cover-a.jpg', 'x.jpg', 'y.jpg', 'cover-b.jpg', 'z.jpg']);
  });

  test('a name used as a cover, in a carousel, or by several rows counts once', () => {
    const rows = [
      { headline: 'A', photo: 'same.jpg', photos: ['same.jpg', 'x.jpg'] },
      { headline: 'B', photos: ['x.jpg', 'same.jpg'] },
    ];
    expect(photoNames(rows)).toEqual(['same.jpg', 'x.jpg']);
  });

  test('a row with a carousel and no cover still lists its photos', () => {
    expect(photoNames([{ headline: 'A', photos: ['x.jpg'] }])).toEqual(['x.jpg']);
  });
});

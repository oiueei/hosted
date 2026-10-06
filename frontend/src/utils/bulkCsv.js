/**
 * Pure CSV-row mapping and validation for the bulk-add flow (BulkAddCsv).
 *
 * Kept i18n-free and component-free so the parsing/validation rules can be unit
 * tested directly. The component wraps `validateRows` to turn the returned key
 * into translated copy. Server-side validators still reject HTML, line breaks
 * and spreadsheet-formula injection per field — this layer only shapes rows and
 * enforces the client-side bounds.
 */

export const MAX_ROWS = 100;

// A thing's extra photos (`Thing.gallery`, "Max 8" on the model and the serializers).
export const MAX_GALLERY = 8;

// The plain text/scalar columns a CSV can carry. `tags` is a single
// `|`-separated cell and `photo` / `photos` are filenames — handled separately.
// `deposit` sits last on purpose: a new column has to land at the end
// of the list, mirroring where it lands in EXAMPLE_CSV's header below — an
// existing CSV missing it simply never sets `raw.deposit`, safely skipped by
// the same `undefined` check every other column already gets.
const COLUMNS = [
  'type',
  'headline',
  'description',
  'fee',
  'availability',
  'location',
  'condition',
  'deposit',
];

/**
 * Map one parsed CSV record to a row payload. `withPhoto` keeps the `photo` filename (the
 * cover) and the `photos` list (the carousel, `|`-separated like `tags`), both resolved
 * against the ZIP at upload time (ZIP path only). Empty/whitespace cells are dropped so
 * they don't overwrite server defaults.
 */
export function mapRow(raw, withPhoto) {
  const row = {};
  for (const col of COLUMNS) {
    const value = raw[col];
    if (value !== undefined && String(value).trim() !== '') {
      row[col] = String(value).trim();
    }
  }
  // Tags are a single cell holding a `|`-separated list (pipe avoids clashing
  // with the CSV field delimiter, which is `;` in some locales).
  if (raw.tags !== undefined && String(raw.tags).trim() !== '') {
    const tags = String(raw.tags)
      .split('|')
      .map((tag) => tag.trim())
      .filter(Boolean);
    if (tags.length > 0) row.tags = tags;
  }
  if (withPhoto && raw.photo !== undefined && String(raw.photo).trim() !== '') {
    row.photo = String(raw.photo).trim();
  }
  if (withPhoto && raw.photos !== undefined) {
    const photos = String(raw.photos)
      .split('|')
      .map((name) => name.trim())
      .filter(Boolean);
    if (photos.length > 0) row.photos = photos;
  }
  return row;
}

/**
 * Shared bounds/required checks. Returns an error KEY ('empty' | 'tooMany' |
 * 'headlineRequired' | 'galleryTooLong') or null when the rows pass. The caller maps the key
 * to copy.
 */
export function validateRows(parsed) {
  if (parsed.length === 0) return 'empty';
  if (parsed.length > MAX_ROWS) return 'tooMany';
  if (parsed.some((row) => !row.headline)) return 'headlineRequired';
  if (parsed.some((row) => (row.photos?.length ?? 0) > MAX_GALLERY)) return 'galleryTooLong';
  return null;
}

/**
 * The distinct photo filenames the rows name, covers and carousels together, in the order
 * they first appear: the files a ZIP import has to find and upload, one ticket each. A name
 * used by several rows, or both as a cover and in a carousel, counts once.
 */
export function photoNames(rows) {
  return [...new Set(rows.flatMap((row) => [row.photo, ...(row.photos ?? [])]).filter(Boolean))];
}

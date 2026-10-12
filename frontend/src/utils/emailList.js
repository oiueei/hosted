/**
 * The addresses in a line of text someone typed or pasted into the invitations field:
 * one, or several separated by commas — `lala@your-domain.test,
 * lele@your-domain.test`. A semicolon separates too (what a mail client writes), and so does
 * any whitespace, line breaks included: an address cannot hold a space, and a browser
 * turns the line breaks of a column pasted into a one-line field into spaces, so
 * "lele1@your-domain.test lili1@your-domain.test" would otherwise be one very odd address. Spaces around an address go
 * away; an address repeated (in any case, as the server lowercases them) counts once, the
 * first spelling kept; nothing between two separators is nothing.
 *
 * The server judges what is and is not an address (`invite/bulk/` reports `invalid` per
 * row); this only cuts the text into the pieces it should judge.
 */
export function parseEmailList(text) {
  const seen = new Set();
  const emails = [];
  for (const piece of String(text ?? '').split(/[\s,;]+/)) {
    if (!piece) continue;
    const key = piece.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    emails.push(piece);
  }
  return emails;
}

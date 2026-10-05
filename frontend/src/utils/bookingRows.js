/**
 * The verb's label in the status cell of the request tables ("Rental", "Reservation"…)
 * tells rows apart only when a table mixes verbs (G9, CA 2026-10-05). Many collections
 * hold one verb alone, and then the label repeated the same word in every row. So it is
 * decided **per table**, by that table's own rows: if all of them are of one verb none
 * carries the label, and if they mix, all of them do. `/my-bookings` and
 * `/owner-bookings` have two tables each (what is waiting or current, and what is past)
 * and each decides for itself. It is computed from the rows at render, so loading more
 * ("Load more") that brings another verb into a table puts the label back on all of its
 * rows. The tag is a column cell, so a phone's cards (`ResponsiveTable`) get the same.
 *
 * Marks every row with `_showType`, which the status column reads; the state label and
 * the "expired" note are not part of this.
 */
export function markMixedVerbs(rows) {
  const mixed = new Set(rows.map((row) => row._type)).size > 1;
  return rows.map((row) => ({ ...row, _showType: mixed }));
}

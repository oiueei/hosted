import { KIND_THING_TYPES } from '../constants/things';

/**
 * What a kind of collection holds, and how a form turns its choices into the
 * `allowed_thing_types` the server stores (`normalize_allowed_thing_types`).
 *
 * A stall and a library have a free verb (give, lend) and a paid one (sell, rent
 * out). A PROPRIETARY one always takes both: its curators put the things in and
 * set each price. A COMMUNITY one takes both when its members may set a price,
 * and only the free one when they may not. A shed takes RESERVE and nothing else.
 */

/** Whether a kind's verbs depend on a price — a stall and a library; a shed books. */
export const hasPriceVerbs = (kind) => kind === 'STALL' || kind === 'LIBRARY';

/** The list a form sends for a kind, a mode and the "members can set a price" switch. */
export function allowedVerbsFor(kind, mode, membersPrice) {
  const verbs = KIND_THING_TYPES[kind] || [];
  if (!hasPriceVerbs(kind)) return verbs;
  return mode === 'COMMUNITY' && !membersPrice ? [verbs[0]] : verbs;
}

/** The switch as a stored list shows it: off only when the list is the free verb alone. */
export function membersPriceFromVerbs(kind, verbs) {
  const list = verbs || [];
  return !(hasPriceVerbs(kind) && list.length === 1 && list[0] === KIND_THING_TYPES[kind][0]);
}

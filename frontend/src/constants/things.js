/**
 * Shared constants for thing types used across the frontend.
 * Display labels are handled by i18n — use t('types.GIFT_THING') etc.
 */

export const TYPE_VALUES = [
  'GIFT_THING',
  'SELL_THING',
  'RENT_THING',
  'LEND_THING',
  'RESERVE_THING',
];

// Types booked by date. RESERVE is date-based too (pickup date + duration), so
// its reserve button navigates to RequestThingPage like LEND/RENT.
export const DATE_TYPES = ['LEND_THING', 'RENT_THING', 'RESERVE_THING'];

// Types whose fee field is REQUIRED and shown.
export const FEE_TYPES = ['SELL_THING', 'RENT_THING'];
// Types whose fee field is shown but OPTIONAL (a space may cost something, or
// nothing). The form shows the input for FEE_TYPES ∪ FEE_OPTIONAL_TYPES and
// requires it only for FEE_TYPES.
export const FEE_OPTIONAL_TYPES = ['RESERVE_THING'];

export const DETAIL_TYPES = ['GIFT_THING', 'SELL_THING', 'LEND_THING', 'RESERVE_THING'];

export const AVAILABILITY_VALUES = ['IMMEDIATE', 'NEXT_WEEK', 'END_OF_MONTH', 'NEXT_MONTH'];

export const CONDITION_VALUES = ['NEW', 'GOOD', 'FAIR', 'USED', 'WELL_USED', 'ALMOST_JUNK'];

// The verbs each kind of collection holds, the browser's copy of the server's
// `KIND_THING_TYPES`: a stall gives or sells, a library lends or rents out, a shed
// books. A collection's `allowed_thing_types` is always within its kind's.
export const KIND_THING_TYPES = {
  STALL: ['GIFT_THING', 'SELL_THING'],
  LIBRARY: ['LEND_THING', 'RENT_THING'],
  SHED: ['RESERVE_THING'],
};

export const TAG_THEMES = {
  taken: { '--tag-background': '#fff4e5', '--tag-color': '#b54708' },
  inactive: { '--tag-background': '#e8e8e8', '--tag-color': '#525252' },
  pending: { '--tag-background': '#fff4e5', '--tag-color': '#b54708' },
  // Owner-defined collection tags assigned to a thing — neutral bussi tint,
  // distinct from the amber status tags and grey inactive tag.
  custom: { '--tag-background': 'var(--color-bus-light)', '--tag-color': 'var(--color-bus)' },
  // "New" signal — summer yellow + black text, AA contrast,
  // warm rather than alarming.
  fresh: { '--tag-background': 'var(--color-summer)', '--tag-color': 'var(--color-black-90)' },
};

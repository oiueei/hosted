/**
 * Shared constants for thing types used across the frontend.
 * Display labels are handled by i18n — use t('types.GIFT_THING') etc.
 */

export const TYPE_VALUES = ['GIFT_THING', 'SELL_THING', 'RENT_THING', 'LEND_THING'];

export const DATE_TYPES = ['LEND_THING', 'RENT_THING'];
export const FEE_TYPES = ['SELL_THING', 'RENT_THING'];

export const DETAIL_TYPES = ['GIFT_THING', 'SELL_THING', 'LEND_THING'];

export const AVAILABILITY_VALUES = ['IMMEDIATE', 'NEXT_WEEK', 'END_OF_MONTH', 'NEXT_MONTH'];

export const CONDITION_VALUES = ['NEW', 'GOOD', 'FAIR', 'USED', 'WELL_USED', 'ALMOST_JUNK'];

// The thing types a collection's allowlist may name. Both modes take the same
// set — mode decides WHO may add a thing, not WHICH types are on offer.
export const ALLOWED_TYPES = ['GIFT_THING', 'SELL_THING', 'RENT_THING', 'LEND_THING'];

export const TAG_THEMES = {
  taken: { '--tag-background': '#fff4e5', '--tag-color': '#b54708' },
  inactive: { '--tag-background': '#e8e8e8', '--tag-color': '#525252' },
  pending: { '--tag-background': '#fff4e5', '--tag-color': '#b54708' },
  // Owner-defined collection tags assigned to a thing — neutral bussi tint,
  // distinct from the amber status tags and grey inactive tag.
  custom: { '--tag-background': 'var(--color-bus-light)', '--tag-color': 'var(--color-bus)' },
  // "New" signal (design round, S7) — summer yellow + black text, AA contrast,
  // warm rather than alarming.
  fresh: { '--tag-background': 'var(--color-summer)', '--tag-color': 'var(--color-black-90)' },
};

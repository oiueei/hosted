/**
 * Shared constants for thing types used across the frontend.
 * Display labels are handled by i18n — use t('types.GIFT_THING') etc.
 */

export const TYPE_VALUES = [
  'GIFT_THING', 'SELL_THING', 'RENT_THING', 'LEND_THING', 'SHARE_THING',
];

export const SHARE_TYPE = 'SHARE_THING';

export const DATE_TYPES = ['LEND_THING', 'RENT_THING'];
export const FEE_TYPES = ['SELL_THING', 'RENT_THING'];

export const DETAIL_TYPES = ['GIFT_THING', 'SELL_THING', 'LEND_THING', 'SHARE_THING'];

export const AVAILABILITY_VALUES = ['IMMEDIATE', 'NEXT_WEEK', 'END_OF_MONTH', 'NEXT_MONTH'];

export const CONDITION_VALUES = ['NEW', 'GOOD', 'FAIR', 'USED', 'WELL_USED', 'ALMOST_JUNK'];

// Collection allow-lists per mode, shared by the Create and Edit collection forms.
export const PROPRIETARY_TYPES = [
  'GIFT_THING', 'SELL_THING', 'RENT_THING', 'LEND_THING',
];
export const COMMUNITY_TYPES = [
  'GIFT_THING', 'SELL_THING', 'RENT_THING', 'LEND_THING', 'SHARE_THING',
];

// is_share forces a single allowed type via its flag — the multi-select still
// renders, but locked and pre-filled.
export const isLockedToSingleType = ({ isShare }) => isShare;

// The set of thing types valid for a given mode/flag combination. The locked
// combination (share) collapses to a single type.
export const allowedTypesFor = ({ mode, isShare }) => {
  if (mode === 'PROPRIETARY') return PROPRIETARY_TYPES;
  if (isShare) return ['SHARE_THING'];
  return COMMUNITY_TYPES;
};

// When the mode/flags change, keep the selection the user already made instead of
// wiping it (P1-5): the locked combination snaps to its forced single type, while
// unlocked ones keep the still-valid intersection of the previous selection.
export const reconcileAllowedTypes = (prev, next) => {
  const valid = allowedTypesFor(next);
  if (isLockedToSingleType(next)) return [...valid];
  return prev.filter((t) => valid.includes(t));
};

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

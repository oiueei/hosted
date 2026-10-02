/**
 * What a member of a collection can really do, as the list of verbs the join door
 * promises ("claim, borrow and add your own things").
 *
 * The door used to say the same four verbs for every collection — request, reserve,
 * ask, add — including where a reservations collection takes no requests and a
 * PROPRIETARY one lets no member add anything. The verbs now come from the
 * collection itself:
 *
 * - the thing types it allows, in the order the cards list them (a list the API
 *   sends in no particular order); an empty list means "no restriction", which is
 *   the four lending-and-giving types — never RESERVE_THING, which always lives
 *   alone in its own collection;
 * - "add your own things", only where members can: COMMUNITY mode.
 *
 * The words are the ones on the cards' buttons (`thingCard.action.*`, in lower
 * case) so the door and the button speak alike. Joined with the language's own
 * conjunction (`Intl.ListFormat`), never with commas by hand: "A, B y C",
 * "A, B i C", "A, B, and C".
 *
 * Returns '' when there is nothing to say (no types the door knows), so the caller
 * can fall back to the generic sentence rather than print a hole.
 */
const VERB_ORDER = ['GIFT_THING', 'SELL_THING', 'LEND_THING', 'RENT_THING', 'RESERVE_THING'];
const UNRESTRICTED = ['GIFT_THING', 'SELL_THING', 'LEND_THING', 'RENT_THING'];

// One literal `t('…')` per verb, not a key built from the type, so the sweep in
// `i18nKeysExist.test.js` can check that each one exists in the catalogues.
const VERB = {
  GIFT_THING: (t) => t('joinToAct.verb.GIFT_THING'),
  SELL_THING: (t) => t('joinToAct.verb.SELL_THING'),
  LEND_THING: (t) => t('joinToAct.verb.LEND_THING'),
  RENT_THING: (t) => t('joinToAct.verb.RENT_THING'),
  RESERVE_THING: (t) => t('joinToAct.verb.RESERVE_THING'),
};

export function joinActions({ allowedThingTypes, mode, t, locale }) {
  const allowed = allowedThingTypes?.length ? allowedThingTypes : UNRESTRICTED;
  const verbs = VERB_ORDER.filter((type) => allowed.includes(type)).map((type) => VERB[type](t));
  if (mode === 'COMMUNITY') verbs.push(t('joinToAct.verb.addOwn'));
  if (verbs.length === 0) return '';
  return new Intl.ListFormat(locale, { type: 'conjunction' }).format(verbs);
}

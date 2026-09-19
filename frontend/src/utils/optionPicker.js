/**
 * Most radios a question may offer before it becomes a dropdown.
 *
 * Eight radios stand about 350px tall — half a phone screen for one question.
 * The hourly reservation's options come from the collection's own numbers: a
 * 15-minute minimum over a 12-hour day offers 48 start times, and a 5-to-720-
 * minute range offers 144 durations. As radios that was a list longer than the
 * page it sat on (DESIGN §4); past this count the same choice is an HDS Select,
 * the control the day-unit flow already uses for its lengths.
 */
export const RADIO_MAX = 8;

/**
 * The element to focus when an OptionPicker's choice is missing on submit: the
 * first radio, or the Select's trigger (HDS gives it the Select's own id plus
 * `-main-button`).
 */
export const optionPickerFocusId = (idPrefix, options) =>
  options.length > RADIO_MAX ? `${idPrefix}-main-button` : `${idPrefix}-${options[0]?.value}`;

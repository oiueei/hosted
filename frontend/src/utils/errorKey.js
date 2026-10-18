/**
 * An error to show later, in the language the reader has *then*.
 *
 * `setError(t('common.connectionError'))` stored the sentence in the language that
 * happened to be current when it failed, so a language switch with the error on
 * screen left it in the old one. A page stores the key (and its parameters) instead
 * and translates where it paints:
 *
 *     setError(errorKey('common.connectionError'));
 *     … {translateError(t, error)} …
 *
 * A plain string is left as it is: it is text the server wrote (a refusal's reason),
 * which has no key to translate.
 */
export const errorKey = (key, params) => ({ key, params });

/** The words of an error held as `errorKey(...)`, or the text itself when it is a string. */
export const translateError = (t, error) => {
  if (!error) return '';
  return typeof error === 'object' ? t(error.key, error.params) : error;
};

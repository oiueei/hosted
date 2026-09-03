/**
 * Loads the help page's questions for one language, and one language only.
 *
 * `LegalPage` imports its three texts eagerly and pays for all of them; this is
 * a dynamic import per language, so a reader downloads the chunk they can
 * actually read. Twelve answers today, and there will be more.
 *
 * The fallback is a genuine last resort rather than a routine path: `i18n`
 * declares `supportedLngs`, so `i18n.language` has already been normalised to
 * one of these three by the time the page asks. It is `en` because that is the
 * app's own `fallbackLng` default — the one place this could disagree with the
 * interface around it, and it does not.
 */

const LOADERS = {
  es: () => import('./es'),
  ca: () => import('./ca'),
  en: () => import('./en'),
};

export function loadFaqEntries(lang) {
  const load = LOADERS[lang] || LOADERS.en;
  return load().then((module) => module.default);
}

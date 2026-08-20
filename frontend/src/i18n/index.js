import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import LanguageDetector from 'i18next-browser-languagedetector';
import en from './locales/en.json';
import { deploymentI18n } from '../deployment';

// English (the fallback language) ships in the main bundle so the very first
// paint is always translated — no key ever flashes and English users fetch
// nothing extra. Spanish and Catalan are ~40 kB each and were bundled eagerly
// too; instead pull them in on demand as their own Vite chunks via this tiny
// i18next backend, so only the active language's file is ever downloaded. A
// Spanish/Catalan visitor sees English for the moment before their chunk lands
// (fallback already in memory), then it swaps in — no spinner, no blank.
// One entry per language that really is a chunk, rather than a
// `./locales/${language}.json` template import. The template also matched
// en.json — which is statically imported above, and has to be — so every build
// warned that the dynamic import "will not move module into another chunk". The
// warning was correct and harmless, which is the worst kind: it never meant
// anything, and it sat there ready to hide the next one that does.
//
// A new language is one more line here, alongside `supportedLngs` and
// `SUPPORTED_LANGUAGES` at the foot of this file.
const LAZY_LOCALES = {
  es: () => import('./locales/es.json'),
  ca: () => import('./locales/ca.json'),
};

const lazyLocaleBackend = {
  type: 'backend',
  init() {},
  read(language, namespace, callback) {
    // en is already in `resources` below and every retired code resolves through
    // `fallbackLng`, so this should only ever be asked for es and ca. Anything
    // else is reported as a failed load rather than answered with an empty
    // bundle: i18next keeps what it already has, which is English.
    const load = LAZY_LOCALES[language];
    if (!load) return callback(new Error(`no lazy locale for ${language}`), false);
    return load()
      .then((mod) => callback(null, mod.default))
      .catch((err) => callback(err, false));
  },
};

i18n
  .use(lazyLocaleBackend)
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    // Retired locales (pt-BR, pt-PT, eu, gl) fall back to es rather than the
    // global default en — closer to the original translation, kept dormant
    // (not deleted) in case they're reinstated. `pt` covers a bare navigator
    // language of "pt" as well as the "pt-*" variants.
    fallbackLng: {
      'pt-BR': ['es'],
      'pt-PT': ['es'],
      pt: ['es'],
      eu: ['es'],
      gl: ['es'],
      default: ['en'],
    },
    supportedLngs: ['en', 'es', 'ca'],
    // Load only the base code (es, not es-ES) so the backend never reaches for a
    // region chunk that doesn't exist.
    load: 'currentOnly',
    // en is bundled while es/ca come from the backend — mixing the two needs
    // this flag so i18next doesn't treat the bundled set as exhaustive.
    partialBundledLanguages: true,
    detection: {
      // Honour a saved choice first, then the browser language; persist the
      // user's pick so it survives reloads and overrides the browser default.
      order: ['localStorage', 'navigator'],
      caches: ['localStorage'],
    },
    resources: {
      en: { translation: en },
    },
    // The fallback (en) is always in memory, so render what we have and swap the
    // active language in when its chunk arrives rather than suspending. Avoids a
    // Suspense-fallback that would itself need translations (LoadingSpinner does).
    react: { useSuspense: false },
    interpolation: { escapeValue: false },
  });

// Copy this deployment adds (frontend/src/deployment). Empty upstream: every
// string the product shows is in `locales/*.json`.
//
// Applied after each language file lands, not once at startup, because es and
// ca arrive later as their own chunks and i18next merges an incoming bundle
// over what is already there — registered only at startup, a deployment's
// strings would survive in English and vanish the moment the visitor's real
// language loaded. Deep merge, overwriting: the deployment's copy is the more
// specific of the two.
function applyDeploymentBundles() {
  Object.entries(deploymentI18n).forEach(([language, bundle]) => {
    // **Only for a language whose own file is already in memory.** Registering a
    // bundle for one that has not loaded yet makes i18next consider that
    // language present and never ask the backend for its chunk — so a
    // deployment that translated three strings into Spanish got those three and
    // the rest of the interface in English, permanently. `en` is in `resources`
    // from the start, es and ca qualify once their chunk lands, which is what
    // the `loaded` handler below is for.
    if (!i18n.hasResourceBundle(language, 'translation')) return;
    i18n.addResourceBundle(language, 'translation', bundle, true, true);
  });
}
applyDeploymentBundles();
i18n.on('loaded', applyDeploymentBundles);

// Language names shown in their own language (endonyms) for the in-app picker.
// Order and codes mirror supportedLngs above. Deliberately not i18n keys — a
// language is always listed in its own language, so these never get translated.
export const SUPPORTED_LANGUAGES = [
  { code: 'en', name: 'English' },
  { code: 'es', name: 'Español' },
  { code: 'ca', name: 'Català' },
];

export default i18n;

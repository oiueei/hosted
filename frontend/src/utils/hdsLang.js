// Map the app's i18n language to a language HDS components understand. HDS ships
// UI strings (Select placeholders, FileInput labels) for a fixed set of locales;
// our supported languages (en/es/ca) aren't all covered, so anything HDS doesn't
// know falls back to English. Finnish/Swedish pass through (HDS is a Helsinki DS).
// Shared by the HDS Select / FileInput / DateInput / Accordion call sites
// (ImageUpload, GalleryUpload, PdfUpload, BulkAddCsv, BulkInviteCsv,
// ShareCollectionMenu, Create/EditCollectionPage, RequestThingPage) so the
// mapping lives in one place — ShareCollectionMenu used to carry its own copy,
// which had already drifted: it sent Swedish to English.
//
// **Known DESIGN §8 gap, not a bug this function can close**: HDS types every
// one of those components' `language` prop as `'en' | 'fi' | 'sv'` — there is
// no prop value this file could return that would render an HDS `DateInput`'s
// month/weekday names, or an `Accordion`'s close-button text, in Spanish or
// Catalan. `es`/`ca` fall back to `en` like any language HDS doesn't cover,
// same as everywhere else this function is used — it just happens that for
// these two components, "falls back to English" is the *only* outcome
// available, for every non-Nordic reader, permanently, not merely until a
// translation ships. Recorded here so it isn't rediscovered as a fresh call
// site bug (found in review, 2026-09-18).
export default function hdsLang(lang) {
  if (lang === 'fi' || lang === 'sv') return lang;
  return 'en';
}

// Map the app's i18n language to a language HDS components understand. HDS ships
// UI strings (Select placeholders, FileInput labels) for a fixed set of locales;
// our supported languages (en/es/ca) aren't all covered, so anything HDS doesn't
// know falls back to English. Finnish/Swedish pass through (HDS is a Helsinki DS).
// Shared by the HDS Select / FileInput call sites (ImageUpload, GalleryUpload,
// PdfUpload, BulkAddCsv, BulkInviteCsv, ShareCollectionMenu) so the mapping
// lives in one place — ShareCollectionMenu used to carry its own copy, which
// had already drifted: it sent Swedish to English.
export default function hdsLang(lang) {
  if (lang === 'fi' || lang === 'sv') return lang;
  return 'en';
}

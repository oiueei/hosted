// Picks html[lang] before React mounts (A3). Mirrors
// i18next-browser-languagedetector's own priority (a saved choice in
// localStorage first, then the browser's own languages) and
// src/i18n/index.js's fallbackLng map — retired locales (pt/eu/gl) land on
// es, not the global en default — so this and i18next never disagree about
// which language a given browser gets. Kept dependency-free and framework-free
// on purpose: it runs before any bundle has loaded.
(function () {
  var SUPPORTED = ['en', 'es', 'ca'];
  var RETIRED_TO_ES = { pt: 'es', eu: 'es', gl: 'es' };

  function resolve(code) {
    var base = (code || '').toLowerCase().split('-')[0];
    if (SUPPORTED.indexOf(base) !== -1) return base;
    return RETIRED_TO_ES[base] || null;
  }

  var lang = null;
  try {
    lang = resolve(window.localStorage.getItem('i18nextLng'));
  } catch (e) {
    // localStorage can throw in a locked-down context (private mode,
    // disabled storage); the browser-language fallback below still works.
  }
  if (!lang && navigator.languages) {
    for (var i = 0; i < navigator.languages.length && !lang; i++) {
      lang = resolve(navigator.languages[i]);
    }
  }
  if (!lang) lang = resolve(navigator.language);
  document.documentElement.lang = lang || 'en';
})();

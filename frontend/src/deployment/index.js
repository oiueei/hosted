/**
 * What this deployment adds to the SPA — the frontend half of the extension
 * points `DEPLOYMENT_URLCONFS` and `CREATOR_POLICY` give the backend.
 *
 * A deployment with pages of its own — an operator's sign-up door, a
 * co-operative's house rules — **replaces this whole directory** rather than
 * editing `App.jsx`, `LoginPage.jsx` or the locale files. That is the point:
 * those are files upstream keeps changing, and a deployment that edits them
 * inherits a merge conflict on every update. A directory it owns outright has
 * none, forever.
 *
 * The same trick already works by accident for `legal/{lang}.js`. Here it is
 * on purpose.
 *
 * @property {Array<{path: string, Component: React.ComponentType}>} deploymentRoutes
 *   Extra SPA routes. `Component` is usually `lazy(() => import(...))` so the
 *   page ships as its own chunk, like every route in `App.jsx`. They mount
 *   **before** the catch-all — see the note there.
 * @property {?string} popInPath
 *   Where the "new here?" button on `/login` and `/welcome` goes, or `null` for
 *   no button at all — which is the honest answer for a deployment whose only
 *   ways in are an invitation and a share link.
 * @property {Object<string, Object>} deploymentI18n
 *   Extra translations, keyed by language code, merged into the `translation`
 *   namespace at startup. A deployment's copy stays out of
 *   `i18n/locales/*.json` this way — three files upstream edits constantly.
 */

export const deploymentRoutes = [];

// No open door here: an account arrives by invitation or by a link somebody
// chose to share, so /login is the whole of the front door and the "new here?"
// button has nowhere to go. A deployment that runs one points this at its own
// page — and it is the only file it has to write to do so.
export const popInPath = null;

export const deploymentI18n = {};

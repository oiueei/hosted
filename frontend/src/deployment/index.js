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
 * @property {?string} aboutPath
 *   Where a page explaining what this deployment *is* lives, or `null` for
 *   none. Two places read it: the site footer links it, and so does the second
 *   button of Home's empty state ("See how it works"), the first screen a
 *   brand-new account sees. Upstream there is no such page: what OIUEEI is
 *   belongs in the README, and a deployment's own answer belongs to the
 *   deployment.
 * @property {?string} faqPath
 *   Where this deployment's help/FAQ page lives, or `null` for none. Linked
 *   from `/login`, the door with the most traffic — upstream has nowhere to
 *   send that link, since a FAQ answers questions about a *particular*
 *   deployment: who operates it, what it lets people create, how to ask for
 *   something it holds back. This repository has no answers to give.
 *   Same shape as `aboutPath`: a link to a 404 is worse than one link fewer.
 * @property {?{contact?: ?Object<string, string>, feedback?: ?Object<string, string>, requestAccess?: ?Object<string, string>}} externalForms
 *   Forms hosted elsewhere that take the place of the app's own ways of writing to
 *   the team (TL1, CA 2026-10-05), or `null` for none — which is upstream, where
 *   nothing changes: `/contact` is the app's own page, "Ideas and bugs" appears only
 *   if `VITE_FEEDBACK_URL` is set, and "Request access" goes where the server's
 *   `capabilities.request_url` says. Each of the three is `{ es, ca, en }`, one URL
 *   per language, or `null` / absent for "there is none"; the page of the reader's
 *   language is opened as it is written here (no parameter is added to it) in a new
 *   tab, and a language without a URL falls back to `es`, and then to nothing.
 *   - `contact`: where the footer's "Contact us" goes, instead of `/contact`.
 *   - `feedback`: "Ideas and bugs", before `VITE_FEEDBACK_URL`.
 *   - `requestAccess`: "Request access", before `capabilities.request_url`.
 *   Core knows nothing about who hosts the forms; this is the same extension point
 *   as `popInPath`, `aboutPath` and `faqPath`.
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

export const aboutPath = null;

export const faqPath = null;

// No forms of its own hosted elsewhere: the app's own pages and the server's answers
// stand (see the docstring). A deployment that has them writes the object here.
export const externalForms = null;

export const deploymentI18n = {};

import { lazy } from 'react';

export { deploymentI18n } from './i18n';

/**
 * What this deployment adds to the SPA.
 *
 * Upstream this directory exports nothing but empties — no routes, no open
 * door, no about page — and `App.jsx`, `LoginPage.jsx`, `SiteFooter.jsx`,
 * `CollectionPage.jsx` and `VerifyPage.jsx` read these four values and are
 * **byte-identical on both branches**. That is the entire point: this file is
 * replaced wholesale, and nothing shared is edited, so a merge from upstream
 * stays a merge.
 *
 * See SELF_HOSTING.md §4.
 */

// Lazy, like every route in App.jsx, so each page ships as its own chunk.
const PopInPage = lazy(() => import('./pages/PopInPage'));
const WelcomePage = lazy(() => import('./pages/WelcomePage'));
const FaqPage = lazy(() => import('./pages/FaqPage'));

export const deploymentRoutes = [
  // The open door: enter an email, get a magic link, land in the demo
  // collections. Its API half is the `hosted` Django app.
  { path: '/popin', Component: PopInPage },
  // What this service is — the personas, the commitment, the example
  // collections. One operator's pitch, which is why it is not upstream.
  { path: '/welcome', Component: WelcomePage },
  // The help page: price, who runs this, what state it is in. Same reason as
  // /welcome — the answers are one operator's, not the product's.
  { path: '/faq', Component: FaqPage },
];

// Where the "new here?" button on /login goes: the page that says what this
// service is (CA, 2026-10-03). The name is upstream's and means "where a
// stranger who is new is sent from /login" — upstream it is the open door
// itself, the only page a newcomer needs, but here the newcomer first reads
// /welcome, whose hero offers both ways on: "New here?" to the open door above
// and "Already have an account?" back to /login. So this is deliberately NOT
// '/popin' any more, though that route is still declared and still reached.
export const popInPath = '/welcome';

// The footer's "what OIUEEI is" link and the second button of Home's empty state
// ("See how it works") — the two places upstream leaves to the deployment.
export const aboutPath = '/welcome';

// The help/FAQ link at the foot of /login, the last thing in the page's content
// (the "trouble signing in?" line that used to sit above it is gone: "Contact us"
// is in the site footer now). Upstream added this fourth slot in the August round
// (S4) for exactly the content this deployment has: what it costs, who runs it,
// what state it is in.
//
// Pointed at the page above now that it answers in all three languages. It was
// deliberately `null` while only Spanish existed: /login is where a stranger
// arrives, and handing them a page in a language they did not choose is a worse
// welcome than one link fewer.
export const faqPath = '/faq';

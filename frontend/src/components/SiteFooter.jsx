import { Link, useLocation } from 'react-router';
import { useTranslation } from 'react-i18next';
import useTheeeme from '../hooks/useTheeeme';

/**
 * The one-line colophon under every page (i14): "Made with ♥︎ in Zona Franca,
 * Barcelona…". Global (mounted once in App), painted with the viewer's theeeme
 * `color_02` — the same token every `.form-page` uses as its background — so
 * there is no colour seam under the 100vh page. `useLocation()` re-renders it
 * on navigation, which re-reads the theeeme after a login/profile change (the
 * pages get this for free by remounting; a permanent component must ask).
 * The heart is U+2665 + U+FE0E (text presentation) so it inherits the text
 * colour instead of turning into a red emoji.
 *
 * **Two links, added in the 2026-08 design round.** `/welcome` was made public
 * precisely so a stranger could read what OIUEEI is, and `/legal` is the page
 * the privacy claims say to go and check — yet every link to either of them sat
 * behind a login (Home's empty state, the invite-only Welcome Linkbox) or on a
 * page only a joiner sees (LoginPage, the pop-in doors). Someone reading a
 * public collection, which is the top of the whole funnel, could reach neither.
 * They stay two plain text links: this is still a colophon, not the HDS
 * `Footer` site-map OIUEEI has no content for (DESIGN §3).
 */
export default function SiteFooter() {
  useLocation();
  const { t } = useTranslation();
  const { tc } = useTheeeme();
  return (
    <footer
      className="site-footer"
      style={tc.color_02 ? { backgroundColor: `var(--color-${tc.color_02})` } : undefined}
    >
      <nav className="site-footer-links" aria-label={t('footer.navLabel')}>
        <Link to="/welcome">{t('footer.about')}</Link>
        <span aria-hidden="true"> · </span>
        <Link to="/legal">{t('footer.legal')}</Link>
      </nav>
      {t('footer.madeIn')}
    </footer>
  );
}

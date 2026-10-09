import { useNavigate } from 'react-router';
import { useTranslation } from 'react-i18next';
import { Linkbox } from 'hds-react';
import { useLocalized } from '../utils/localized';

/**
 * A collection row (HDS Linkbox, no thumbnail) used in the collection grids
 * on HomePage (My / Inactive / Shared with me) and on a public profile
 * (collections in common). Clicking navigates client-side to the collection.
 * Deliberately image-less — thing cards keep their thumbnail, so a full-width
 * text-only row is what visually tells collections and things apart; a
 * collection's own thumbnail now lives on its `CollectionPage` hero instead
 * (`HeroPhoto`, see S7/S8).
 *
 * Props:
 *   collection – { code, headline, things?, invites? }
 *   showInfo   – show the "{N} things · {N} guests" line (the Home grids pass
 *                counts; the profile grid omits it). Requires things/invites.
 */
export default function CollectionLinkbox({ collection, showInfo = false }) {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const headline = useLocalized()(collection.headline);
  return (
    <Linkbox
      href={`/collections/${collection.code}`}
      onClick={(e) => {
        // A plain left click routes in-app; any click that means "somewhere
        // else, not here" — a new tab or window, a download — is the browser's,
        // which is why the href is real. The same rule `ButtonLink` keeps. It
        // must also stop here: HDS's Linkbox listens on its outer region and
        // answers any click there with a fresh `.click()` on this link, with no
        // modifier keys — which would open the new tab *and* move this one.
        if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) {
          e.stopPropagation();
          return;
        }
        e.preventDefault();
        navigate(`/collections/${collection.code}`);
      }}
      heading={headline}
      text={
        showInfo
          ? t('userPage.collectionInfo', {
              things: collection.things.length,
              guests: collection.invites.length,
            })
          : undefined
      }
      linkAriaLabel={t('userPage.viewCollection', { headline })}
      linkboxAriaLabel={headline}
      border
      size="small"
    />
  );
}

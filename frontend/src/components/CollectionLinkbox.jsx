import { useNavigate } from 'react-router';
import { useTranslation } from 'react-i18next';
import { Linkbox } from 'hds-react';
import { useLocalized } from '../utils/localized';
import { collectionPath } from '../utils/collectionPath';

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
 *   collection – { code, kind?, headline, things?, invites? }
 *   showInfo   – show the "{N} things · {N} members" counts after the kind (the Home grids pass
 *                counts; the profile grid omits it). Requires things/invites.
 */
export default function CollectionLinkbox({ collection, showInfo = false }) {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const headline = useLocalized()(collection.headline);
  // What it is, then what it holds: "Library · 3 things · 5 members". The profile's
  // row has no counts and names only the kind; a collection read without its kind
  // (an older response) says what it always did.
  const text =
    [
      collection.kind && t(`kinds.${collection.kind}.short`),
      ...(showInfo
        ? [
            t('userPage.thingsCount', { count: collection.things.length }),
            t('userPage.membersCount', { count: collection.invites.length }),
          ]
        : []),
    ]
      .filter(Boolean)
      .join(' · ') || undefined;
  return (
    <Linkbox
      href={collectionPath(collection.code, collection.kind)}
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
        navigate(collectionPath(collection.code, collection.kind));
      }}
      heading={headline}
      text={text}
      linkAriaLabel={t('userPage.viewCollection', { headline })}
      linkboxAriaLabel={headline}
      border
      size="small"
    />
  );
}

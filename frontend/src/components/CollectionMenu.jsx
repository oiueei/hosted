import { useRef, useState } from 'react';
import { Link } from 'react-router';
import { useTranslation } from 'react-i18next';
import { IconMenuDots, Notification } from 'hds-react';
import useDismissable from '../hooks/useDismissable';
import StatusRegion from './StatusRegion';

const PANEL_ID = 'collection-menu-panel';

/**
 * The collection's own options, one click from its page (CA, 2026-10-03):
 * "Add thing" and "Manage members" used to crowd the hero beside "Edit
 * collection", and the two data downloads lived at the foot of the settings
 * page — so a curator ran the group from three places at once. The hero row
 * keeps "Edit collection" alone; everything else is this menu, a fourth
 * icon in the hero's corner (`AccountMenu` · this · `ShareCollectionMenu` ·
 * `ContactCorner`), shown to curators only (owner or co-owner, `is_curator`
 * — the server's own word, the same gate the row uses).
 *
 * The panel mixes links with the three download buttons, so it is a plain
 * `<div>` — not the account menu's `<nav>` (this is not all navigation)
 * and not `role="menu"` (that role expects arrow keys between actions;
 * these are ordinary Tab-reachable controls — the same reasoning as
 * `AccountMenu`, which spells it out). No `aria-label` either: an
 * unnamed `<div>` is fine, and axe flags the label on a div with no role.
 *
 * The downloads themselves belong to `useCollectionDownloads`, which the
 * page calls once and hands here and to `CollectionDownloadsStatus`; the
 * calendar entry appears only where the group holds date-based things
 * (`hasDateThings`, the rule the hero button always used). The JSON
 * download is **direct, no warning** (CA, 2026-10-03): the privacy notice
 * it used to carry at the settings page's foot went with it — whoever
 * runs a group should already know what its copy holds, and the place to
 * say so is a curator rights-and-obligations page that does not exist yet
 * (noted in `CA_TASKS.md`).
 */
export default function CollectionMenu({ code, hasDateThings, downloads }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const wrapperRef = useRef(null);
  const buttonRef = useRef(null);
  useDismissable({ open, setOpen, wrapperRef, buttonRef });
  const { calendar, stats, collectionExport } = downloads;

  const label = t('collectionMenu.label');
  // Following any entry closes the panel, as in the account menu. A
  // download also returns focus to the trigger: the pressed button
  // disappears with the panel, and the focus would fall to <body> while
  // the file it asked for is still being fetched.
  const close = () => setOpen(false);
  const runAndClose = (download) => () => {
    setOpen(false);
    buttonRef.current?.focus();
    download();
  };

  return (
    <span className="collection-menu" ref={wrapperRef}>
      <button
        type="button"
        ref={buttonRef}
        className="collection-menu-trigger"
        aria-label={label}
        aria-expanded={open}
        aria-controls={open ? PANEL_ID : undefined}
        onClick={() => setOpen((v) => !v)}
      >
        <IconMenuDots aria-hidden="true" />
      </button>
      {open && (
        <div id={PANEL_ID} className="collection-menu-panel">
          <Link to={`/collections/${code}/add`} onClick={close}>
            {t('collectionPage.addThing')}
          </Link>
          <Link to={`/collections/${code}/invites`} onClick={close}>
            {t('collectionPage.manageGuests')}
          </Link>
          <hr className="collection-menu-divider" />
          {hasDateThings && (
            <button
              type="button"
              disabled={calendar.downloading}
              onClick={runAndClose(calendar.download)}
            >
              {t('calendarExport.downloadButton')}
            </button>
          )}
          <button type="button" disabled={stats.downloading} onClick={runAndClose(stats.download)}>
            {t('stats.downloadStats')}
          </button>
          <button
            type="button"
            disabled={collectionExport.downloading}
            onClick={runAndClose(collectionExport.download)}
          >
            {t('collectionExport.downloadButton')}
          </button>
        </div>
      )}
    </span>
  );
}

/**
 * The outcome zone for the menu's three downloads, under the hero's
 * "Edit collection" row (where the calendar's used to sit). One message at
 * a time: it renders the state of the download that last started —
 * "Preparing the file…" while it runs, then that download's own result
 * (the calendar's counts; a failure's reason; a stats download that
 * succeeds says nothing, as it always didn't). The `StatusRegion` renders
 * unconditionally so it pre-dates its own content, which is what makes a
 * screen reader announce it.
 */
export function CollectionDownloadsStatus({ downloads }) {
  const { t } = useTranslation();
  const { active, calendar, stats, collectionExport } = downloads;
  const downloading =
    (active === 'calendar' && calendar.downloading) ||
    (active === 'stats' && stats.downloading) ||
    (active === 'collectionExport' && collectionExport.downloading);
  const error =
    !downloading && active === 'calendar'
      ? calendar.error
      : !downloading && active === 'stats' && stats.error
        ? t('stats.downloadStatsError')
        : !downloading && active === 'collectionExport'
          ? collectionExport.error
          : null;
  const info = !downloading && active === 'calendar' ? calendar.info : null;

  return (
    <StatusRegion>
      {downloading && (
        <Notification type="info" size="small" style={{ marginTop: 'var(--spacing-xs)' }}>
          {t('collectionExport.downloading')}
        </Notification>
      )}
      {error && (
        <Notification type="error" size="small" style={{ marginTop: 'var(--spacing-xs)' }}>
          {error}
        </Notification>
      )}
      {info && (
        <Notification type="success" size="small" style={{ marginTop: 'var(--spacing-xs)' }}>
          {info}
        </Notification>
      )}
    </StatusRegion>
  );
}

import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router';
import { useTranslation } from 'react-i18next';
import { IconUser } from 'hds-react';

const PANEL_ID = 'account-menu-panel';

/**
 * The account's own pages, one click away from every hero (CA + an early
 * adopter, 2026-09-28): "My profile", "Edit profile", "Create collection",
 * "My requests", "Requests to me" and "Log out" used to live only on `/` and
 * `/me` — hard to reach from inside a collection, and **unreachable at all**
 * from one whose owner set a `home_page`, since that hero's own "Home" link
 * leaves OIUEEI for the group's own site.
 *
 * A plain navigation disclosure — a button that shows/hides a `<nav>` of
 * `Link`s — not `ShareCollectionMenu`'s HDS-`Select`-as-menu trick: every
 * option here is a **route**, not an action, and a `Select` announces itself
 * as a combobox to a screen reader (already flagged as an A1 risk in
 * `CA_TASKS.md`). No `role="menu"` either — that role expects arrow-key
 * navigation between actions; this is `Tab`-navigable links, so the native
 * semantics already say what it is.
 *
 * Rendered next to `ContactCorner` (and, on `CollectionPage`, `ShareCollectionMenu`)
 * inside the shared `.hero-corners` flex row — see `PageLayout` and the eight
 * manual-hero pages for where. **Session-gated, not page-gated**: it reads
 * `userCode` itself and renders nothing for a signed-out visitor, so it needs
 * no prop from any of its many call sites.
 */
export default function AccountMenu() {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const wrapperRef = useRef(null);
  const buttonRef = useRef(null);

  // Escape closes and returns focus to the trigger (WCAG 1.4.13's
  // "dismissible", the same shape InfoPopover uses); a click outside the
  // wrapper closes without moving focus at all. Both listeners live on
  // `document` and only while the panel is open, and neither stops
  // propagation, so an ancestor dialog still gets its own Escape.
  useEffect(() => {
    if (!open) return undefined;
    const onKeyDown = (e) => {
      if (e.key !== 'Escape') return;
      setOpen(false);
      buttonRef.current?.focus();
    };
    const onPointerDown = (e) => {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target)) {
        setOpen(false);
      }
    };
    document.addEventListener('keydown', onKeyDown);
    document.addEventListener('mousedown', onPointerDown);
    return () => {
      document.removeEventListener('keydown', onKeyDown);
      document.removeEventListener('mousedown', onPointerDown);
    };
  }, [open]);

  // Read directly, like every other per-viewer check in this app (ThingLinkbox,
  // CollectionPage, …) — no context, no prop, so every hero can render this
  // unconditionally and let it decide for itself.
  const userCode = localStorage.getItem('userCode');
  if (!userCode) return null;

  const label = t('accountMenu.label');

  return (
    <span className="account-menu" ref={wrapperRef}>
      <button
        type="button"
        ref={buttonRef}
        className="account-menu-trigger"
        aria-label={label}
        aria-expanded={open}
        aria-controls={open ? PANEL_ID : undefined}
        onClick={() => setOpen((v) => !v)}
      >
        <IconUser aria-hidden="true" />
      </button>
      {open && (
        <nav id={PANEL_ID} className="account-menu-panel" aria-label={label}>
          <Link to="/">{t('common.home')}</Link>
          <Link to="/me">{t('home.myProfile')}</Link>
          <Link to="/me/edit">{t('userPage.editProfile')}</Link>
          <Link to="/collections/new">{t('home.createCollection')}</Link>
          <Link to="/my-bookings">{t('home.myRequests')}</Link>
          <Link to="/owner-bookings">{t('home.requestsToMe')}</Link>
          <hr className="account-menu-divider" />
          <Link to="/logout">{t('userPage.logout')}</Link>
        </nav>
      )}
    </span>
  );
}

import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router';
import { useTranslation } from 'react-i18next';
import { IconUser } from 'hds-react';
import { apiFetch } from '../services/api';

const PANEL_ID = 'account-menu-panel';

/**
 * The account's own pages, one click away from every hero (CA + an early
 * adopter, 2026-09-28): "My profile", "My requests", "Requests to me" and "Log
 * out", under "Home", used to live only on `/` and `/me` — hard to reach from
 * inside a collection, and **unreachable at all** from one whose owner set a
 * `home_page`, since that hero's own "Home" link leaves OIUEEI for the group's
 * own site.
 *
 * "Edit profile" and "Create collection" are not here (CA, 2026-10-02): the first
 * is reached from "My profile", the second from Home. And "Requests to me" is
 * shown only to someone who can receive requests — owns a thing, or runs a
 * PROPRIETARY collection — which only the server knows, so the menu asks
 * `GET /auth/me/` (`receives_requests`) when it opens. Nothing is kept in the
 * browser for it (a new storage key is one more line in the `/legal`), and while
 * the answer is not there, or if it cannot be had, the link is left out.
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
  const [receivesRequests, setReceivesRequests] = useState(false);

  // Asked each time the panel opens, so an account that has just got its first
  // thing, or been made a curator, sees the link without a reload.
  useEffect(() => {
    if (!open) return undefined;
    const controller = new AbortController();
    const { signal } = controller;
    const ask = async () => {
      try {
        const res = await apiFetch('/api/v1/auth/me/', { signal });
        if (!res.ok) return;
        const data = await res.json();
        if (!signal.aborted) setReceivesRequests(data.receives_requests === true);
      } catch {
        // No answer, no link: guessing would put a dead page back in the menu.
      }
    };
    ask();
    return () => controller.abort();
  }, [open]);

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
  // Following any link closes the panel: one to the page already on screen
  // (Home from `/`, My profile from `/me`) keeps this component mounted, and
  // the panel would otherwise stay open over the page it just "went" to.
  const close = () => setOpen(false);

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
          <Link to="/" onClick={close}>
            {t('common.home')}
          </Link>
          <Link to="/me" onClick={close}>
            {t('home.myProfile')}
          </Link>
          <Link to="/my-bookings" onClick={close}>
            {t('home.myRequests')}
          </Link>
          {receivesRequests && (
            <Link to="/owner-bookings" onClick={close}>
              {t('home.requestsToMe')}
            </Link>
          )}
          <hr className="account-menu-divider" />
          <Link to="/logout" onClick={close}>
            {t('userPage.logout')}
          </Link>
        </nav>
      )}
    </span>
  );
}

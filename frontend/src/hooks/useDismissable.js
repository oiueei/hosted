import { useEffect } from 'react';

/**
 * The shared dismissal behaviour of the hero's disclosure menus: Escape closes
 * and returns focus to the trigger (WCAG 1.4.13's "dismissible", the same
 * shape InfoPopover uses); a `mousedown` outside the wrapper closes without
 * moving focus at all. Both listeners live on `document` and only while the
 * panel is open, and neither stops propagation, so an ancestor dialog still
 * gets its own Escape.
 *
 * Extracted from `AccountMenu` (2026-10-03): the collection menu joining it
 * in the hero's corner needed exactly this contract, and two copies of a
 * focus promise is one copy too many.
 */
export default function useDismissable({ open, setOpen, wrapperRef, buttonRef }) {
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
  }, [open, setOpen, wrapperRef, buttonRef]);
}

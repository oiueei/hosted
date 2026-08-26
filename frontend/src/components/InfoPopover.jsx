import { useEffect, useState } from 'react';
import { Notification, IconInfoCircleFill } from 'hds-react';

/**
 * (i) icon button that reveals an info panel on hover/focus/click, closing on
 * mouse-leave/blur/Escape. The positioning class (`.info-popover-panel`, in App.css)
 * lives on the wrapper `<div>` below — never pass a positioning class as
 * `className` to the HDS `Notification` itself. Its rendered root carries
 * HDS's own `position: relative` at the same selector specificity as a
 * single custom class, so which one wins depends on unpredictable
 * style-injection order (this was BulkInviteCsv's original bug: the panel
 * sometimes rendered in flow instead of absolutely positioned).
 *
 * Props:
 *   title – panel label (also the button's accessible name)
 *   children – panel body
 *   id – id for the panel wrapper, referenced by aria-controls while open
 */
export default function InfoPopover({ title, children, id }) {
  const [open, setOpen] = useState(false);

  // WCAG 1.4.13 "dismissible": the panel appears on hover and on focus, so it
  // must be closable without moving the pointer or the focus — otherwise it can
  // sit over the field below it with no way out for a keyboard user. Escape
  // closes it and leaves focus on the button; the next deliberate hover, focus
  // or click opens it again, so a dismissal is never sticky.
  //
  // The listener is on `document`, not on the wrapper: a mouse user hovering the
  // (i) usually has focus somewhere else entirely, so a wrapper-level handler
  // would only ever fire for the keyboard case. Attached only while the panel is
  // up, and it does not stop propagation — an ancestor dialog still gets its own
  // Escape.
  //
  // Unlike `TooltipButton`, this needs no separate `dismissed` flag. That bubble
  // has no toggle of its own, so it must tell "not hovered" apart from
  // "dismissed"; here `open` already *is* the button's disclosure state, which
  // means closing it is the dismissal and `aria-expanded` stays truthful for
  // free.
  useEffect(() => {
    if (!open) return undefined;
    const onKeyDown = (e) => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [open]);

  return (
    // The span is a passive wrapper, not an interactive target: the real
    // button below does all the keyboard/aria work, and its own focus/blur
    // bubble up here to control visibility, so nothing here needs independent
    // keyboard support of its own.
    // eslint-disable-next-line jsx-a11y/no-static-element-interactions
    <span
      className="info-popover"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
    >
      <button
        type="button"
        className="info-popover-button"
        aria-label={title}
        aria-expanded={open}
        aria-controls={open ? id : undefined}
        onClick={() => setOpen((v) => !v)}
      >
        <IconInfoCircleFill aria-hidden="true" />
      </button>
      {open && (
        <div id={id} className="info-popover-panel">
          <Notification type="info" size="small" label={title}>
            {children}
          </Notification>
        </div>
      )}
    </span>
  );
}

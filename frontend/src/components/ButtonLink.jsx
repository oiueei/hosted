import { Link as HdsLink } from 'hds-react';
import { useHref, useNavigate } from 'react-router';

/**
 * A control that navigates and looks like a button — one `<a>`, one tab stop.
 *
 * It replaces `<Link to=…><Button/></Link>`, which put one interactive element
 * inside another: two tab stops for one control, announced "link… button", the
 * `<a>` taking the focus ring while the `<button>` carried the look. Twenty-three
 * of them had accumulated, because `jest-axe` reports no violation for the shape
 * and `eslint-plugin-jsx-a11y` has no rule for it. `nestedInteractive.js` is the
 * invariant that now does.
 *
 * This is HDS's own answer, not a hand-rolled button: `Link`'s `useButtonStyles`
 * swaps the link class for `hds-button hds-button--primary`, the real button CSS
 * with the same `--computed-*` token chain. So the theeeme styles from
 * `useTheeeme` apply exactly as they did — including `btnSecondaryStyle`, since
 * what makes a secondary button here is the token set, not HDS's variant class
 * (which is why there is no `variant` prop below).
 *
 * `to` is a router path, resolved through `useHref` so a relative target and a
 * future basename behave as they do everywhere else. The click handler is what
 * makes it a client-side navigation, and it deliberately **only** intercepts a
 * plain left click: a modified or middle click falls through to the real `href`,
 * so open-in-new-tab, open-in-new-window and copy-link keep working. Losing that
 * is the usual cost of hand-rolling this, and it is precisely the thing a real
 * link was supposed to buy.
 *
 * Props: `to`, `state` (both forwarded to `navigate`), `fullWidth`, plus `style`
 * (the theeeme tokens) and anything else, which reaches the `<a>`.
 */
export default function ButtonLink({ to, state, fullWidth = false, className, ...rest }) {
  const navigate = useNavigate();
  const href = useHref(to);

  return (
    <HdsLink
      href={href}
      useButtonStyles
      className={[fullWidth ? 'button-link--full' : '', className].filter(Boolean).join(' ')}
      onClick={(event) => {
        if (event.defaultPrevented) return;
        // Let the browser have every click that means "somewhere else, not here".
        if (event.button !== 0) return;
        if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
        event.preventDefault();
        navigate(to, state ? { state } : undefined);
      }}
      {...rest}
    />
  );
}

import { Link } from 'react-router';
import { IconArrowLeft, IconLinkExternal } from 'hds-react';

export default function BackLink({ to, href, label }) {
  // An external destination — a collection's own `home_page` — can't go through
  // react-router; it's a plain anchor that leaves the app. The caller sanitizes
  // the URL and only passes `href` when it's a real http(s) address. It also
  // gets an external-link icon and the caller names the destination, so it does
  // not read as "back to the OIUEEI home" (it isn't).
  if (href) {
    return (
      <a href={href} className="back-link section-mt" rel="noopener noreferrer">
        <IconArrowLeft aria-hidden="true" /> {label} <IconLinkExternal aria-hidden="true" />
      </a>
    );
  }
  const inner = (
    <>
      <IconArrowLeft aria-hidden="true" /> {label}
    </>
  );
  return (
    <Link to={to} className="back-link section-mt">
      {inner}
    </Link>
  );
}

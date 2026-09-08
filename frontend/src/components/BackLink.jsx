import { Link } from 'react-router';
import { IconArrowLeft } from 'hds-react';

export default function BackLink({ to, href, label }) {
  const inner = (
    <>
      <IconArrowLeft aria-hidden="true" /> {label}
    </>
  );
  // An external destination — a collection's own `home_page` — can't go through
  // react-router; it's a plain anchor that leaves the app. The caller sanitizes
  // the URL and only passes `href` when it's a real http(s) address.
  if (href) {
    return (
      <a href={href} className="back-link section-mt" rel="noopener noreferrer">
        {inner}
      </a>
    );
  }
  return (
    <Link to={to} className="back-link section-mt">
      {inner}
    </Link>
  );
}

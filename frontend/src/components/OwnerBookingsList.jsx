import { useTranslation } from 'react-i18next';
import { useLocalized } from '../utils/localized';
import { formatDate, formatBookingWhen } from '../utils/rental';

/**
 * Owner-only list of a thing's future bookings (pending + confirmed), shared by
 * ThingPage and ThingLinkbox. The active pending booking is bold and starred with
 * `*` when more than one pending booking exists. Renders nothing unless the viewer
 * is the owner and there is at least one booking.
 */
export default function OwnerBookingsList({ bookings, activePendingCode, isOwner, thingType }) {
  const { t } = useTranslation();
  // Hooks run before the early return — an offered thing's headline may be a
  // per-language map like any other owner content.
  const L = useLocalized();
  if (!isOwner || bookings.length === 0) return null;

  const pendingCount = bookings.filter((b) => b.status === 'PENDING').length;
  return (
    <ul className="thing-card-bookings">
      {bookings.map((b) => {
        const isActive = isOwner && b.code === activePendingCode;
        const showStar = isActive && pendingCount > 1;
        // The calendar rows carry no thing type; the card knows it, and a
        // day-unit reservation's range depends on it (formatBookingWhen).
        const when = formatBookingWhen(b, b.thing_type || thingType);
        return (
          <li key={b.code} style={{ fontWeight: isActive ? 'bold' : 'normal' }}>
            {isOwner && b.requester_name && <>{b.requester_name}. </>}
            {b.created && <>{formatDate(b.created)}. </>}
            {when && <>{when}</>}{' '}
            <span
              style={{
                color: b.status === 'ACCEPTED' ? 'var(--color-success)' : 'var(--color-alert-dark)',
              }}
            >
              ({b.status === 'ACCEPTED' ? t('thingCard.confirmed') : t('thingCard.pending')})
              {showStar ? ' *' : ''}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

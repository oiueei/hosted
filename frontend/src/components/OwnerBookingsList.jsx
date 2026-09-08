import { useTranslation } from 'react-i18next';
import { useLocalized } from '../utils/localized';
import { formatDate } from '../utils/rental';

/**
 * Owner-only list of a thing's future bookings (pending + confirmed), shared by
 * ThingPage and ThingLinkbox. The active pending booking is bold and starred with
 * `*` when more than one pending booking exists. Renders nothing unless the viewer
 * is the owner and there is at least one booking.
 */
export default function OwnerBookingsList({ bookings, activePendingCode, isOwner }) {
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
        return (
          <li key={b.code} style={{ fontWeight: isActive ? 'bold' : 'normal' }}>
            {isOwner && b.requester_name && <>{b.requester_name}. </>}
            {b.created && <>{formatDate(b.created)}. </>}
            {b.start_date && b.end_date && (
              <>
                {formatDate(b.start_date)} – {formatDate(b.end_date)}
              </>
            )}{' '}
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

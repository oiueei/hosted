import { useEffect, useState } from 'react';
import { Link } from 'react-router';
import { useTranslation } from 'react-i18next';
import { Button, Dialog, Notification, StatusLabel, Tag, Table, IconCheck, IconCrossCircle } from 'hds-react';
import { DATE_TYPES } from '../constants/things';
import { apiFetch } from '../services/api';
import PageLayout from '../components/PageLayout';
import LoadingSpinner from '../components/LoadingSpinner';
import Toast from '../components/Toast';
import TooltipButton from '../components/TooltipButton';
import useTheeeme from '../hooks/useTheeeme';
import { useLocalized } from '../utils/localized';

/**
 * The owner's side of MyBookingsPage: every request made on their things, in one
 * place, answerable from here.
 *
 * The asymmetry this closes: a requester has always had /my-bookings, while an
 * owner had only the email, an inbox banner, or opening each collection in turn.
 * An owner with five collections had no single answer to "who is waiting on me?".
 * `GET /api/v1/owner-bookings/` existed and was documented all along — nothing in
 * the frontend called it.
 *
 * Mirrors MyBookingsPage deliberately (same table shape, same pending/past split,
 * same pager) so the two sides of a booking read the same way; the differences
 * are the column showing who asked rather than who owns, and the actions being
 * accept/reject rather than cancel.
 */
const STATUS_TYPES = {
  PENDING: 'alert',
  ACCEPTED: 'success',
  REJECTED: 'error',
  CANCELLED: 'neutral',
  EXPIRED: 'neutral',
};

export default function OwnerBookingsPage() {
  const { t, i18n } = useTranslation();
  const L = useLocalized();
  const { tc, btnStyle, btnSecondaryStyle } = useTheeeme();
  const [bookings, setBookings] = useState(null);
  const [next, setNext] = useState(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState('');
  const [toast, setToast] = useState(null);
  const [acting, setActing] = useState(null);
  // The row whose acceptance would hand the thing over for good, pending
  // confirmation. Accepting a GIFT or SELL that isn't endless flips it INACTIVE,
  // adds the requester to `deal` and writes a ThingTransfer — the owner no
  // longer has it, and there is no undo. A loan, a rental and an endless
  // give-away all come back or never run out, so those accept straight away.
  const [transferRow, setTransferRow] = useState(null);
  useEffect(() => { document.title = t('titles.ownerBookings'); }, [t]);

  const STATUS_LABELS = {
    PENDING: t('myBookings.statusPending'),
    ACCEPTED: t('myBookings.statusConfirmed'),
    REJECTED: t('myBookings.statusRejected'),
    CANCELLED: t('myBookings.statusCancelled'),
    EXPIRED: t('myBookings.statusExpired'),
  };

  useEffect(() => {
    const fetchBookings = async () => {
      try {
        const res = await apiFetch('/api/v1/owner-bookings/');
        if (res.ok) {
          const data = await res.json();
          setBookings(data.results);
          setNext(data.next || null);
        } else {
          setError(t('ownerBookings.errorLoading'));
        }
      } catch {
        setError(t('common.connectionError'));
      }
    };
    fetchBookings();
  }, [t]);

  const handleAction = async (bookingCode, action) => {
    setActing(bookingCode);
    try {
      const res = await apiFetch(`/api/v1/bookings/${bookingCode}/${action}/`, { method: 'POST' });
      if (res.ok) {
        setBookings((prev) =>
          prev.map((b) =>
            b.code === bookingCode
              ? { ...b, status: action === 'accept' ? 'ACCEPTED' : 'REJECTED' }
              : b,
          ),
        );
        setToast({
          type: 'success',
          message: action === 'accept'
            ? t('ownerBookings.accepted')
            : t('ownerBookings.rejected'),
        });
      } else {
        setToast({ type: 'error', message: t('ownerBookings.errorActing') });
      }
    } catch {
      setToast({ type: 'error', message: t('common.connectionError') });
    } finally {
      setActing(null);
    }
  };

  const loadMore = async () => {
    if (!next || loadingMore) return;
    setLoadingMore(true);
    try {
      // `next` is an absolute DRF URL; strip the origin so it goes through the
      // Vite proxy in dev and stays same-origin (sends auth cookies) everywhere.
      const path = next.replace(/^https?:\/\/[^/]+/, '');
      const res = await apiFetch(path);
      if (res.ok) {
        const data = await res.json();
        setBookings((prev) => [...prev, ...(data.results || [])]);
        setNext(data.next || null);
      }
    } catch {
      setToast({ type: 'error', message: t('common.connectionError') });
    } finally {
      setLoadingMore(false);
    }
  };

  if (error) {
    return (
      <PageLayout title={t('common.error')} backTo="/" backLabel={t('common.home')}>
        <Notification label={t('common.error')} type="error">{error}</Notification>
      </PageLayout>
    );
  }

  if (!bookings) return <LoadingSpinner />;

  const rows = bookings.map((b) => ({
    _id: b.code,
    _code: b.code,
    _type: b.thing_type,
    _status: b.status,
    _thingCode: b.thing_code,
    _thingHeadline: L(b.thing_headline) || b.thing_code,
    _requesterName: b.requester_name,
    _startDate: b.start_date,
    _endDate: b.end_date,
    _created: b.created,
    _transfersOwnership: !DATE_TYPES.includes(b.thing_type) && !b.thing_is_endless,
  }));

  const cols = [
    {
      key: '_thing',
      headerName: t('ownerBookings.colRequest'),
      transform: (row) => (
        <div>
          <Link to={`/things/${row._thingCode}`}>{row._thingHeadline}</Link>
          {row._requesterName && (
            <p style={{ margin: 'var(--spacing-2-xs) 0 0', fontSize: 'var(--fontsize-body-s)' }}>
              {t('ownerBookings.requestedBy', { name: row._requesterName })}
            </p>
          )}
          <p style={{ margin: 'var(--spacing-2-xs) 0 0', fontSize: 'var(--fontsize-body-s)', color: 'var(--color-black-50)' }}>
            {t('myBookings.requested', { date: new Date(row._created).toLocaleDateString(i18n.language) })}
          </p>
          <p style={{ margin: 'var(--spacing-2-xs) 0 0', fontSize: 'var(--fontsize-body-s)' }}>
            {row._startDate && row._endDate
              ? `${new Date(row._startDate).toLocaleDateString(i18n.language)} — ${new Date(row._endDate).toLocaleDateString(i18n.language)}`
              : <span style={{ color: 'var(--color-black-40)' }}>{t('myBookings.noDates')}</span>}
          </p>
        </div>
      ),
    },
    {
      key: '_status',
      headerName: t('myBookings.colStatus'),
      transform: (row) => (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--spacing-2-xs)' }}>
          <Tag>{t('types.' + row._type)}</Tag>
          <StatusLabel type={STATUS_TYPES[row._status] || 'neutral'}>
            {STATUS_LABELS[row._status] || row._status}
          </StatusLabel>
        </div>
      ),
    },
    {
      key: '_actions',
      headerName: '',
      transform: (row) => row._status === 'PENDING' ? (
        <div style={{ display: 'flex', gap: 'var(--spacing-xs)', justifyContent: 'flex-end' }}>
          <TooltipButton
            tooltip={t('ownerBookings.acceptTooltip')}
            onClick={() => (row._transfersOwnership
              ? setTransferRow(row)
              : handleAction(row._code, 'accept'))}
            disabled={acting === row._code}
          >
            <IconCheck aria-hidden />
          </TooltipButton>
          <TooltipButton
            tooltip={t('ownerBookings.rejectTooltip')}
            onClick={() => handleAction(row._code, 'reject')}
            disabled={acting === row._code}
          >
            <IconCrossCircle aria-hidden />
          </TooltipButton>
        </div>
      ) : null,
    },
  ];

  const pendingRows = rows.filter((r) => r._status === 'PENDING');
  const otherRows = rows.filter((r) => r._status !== 'PENDING');
  const tableTheme = tc.color_03
    ? { '--header-background-color': `var(--color-${tc.color_03})` }
    : undefined;

  return (
    <PageLayout title={t('ownerBookings.pageTitle')} backTo="/" backLabel={t('common.home')}>
      {bookings.length === 0 ? (
        <div>
          <p>{t('ownerBookings.noBookings')}</p>
          <div className="spacer-m" />
          {/* Its own copy, not the requester page's "Browse collections": an
              owner with no requests wants to get their things in front of
              somebody, not to go shopping. */}
          <Link to="/">
            <Button style={btnStyle}>{t('ownerBookings.emptyCta')}</Button>
          </Link>
        </div>
      ) : (
        <>
          <h2>{t('ownerBookings.waitingOnYou')}</h2>
          <div className="spacer-s" />
          {pendingRows.length === 0 ? (
            <p className="text-muted">{t('ownerBookings.noPending')}</p>
          ) : (
            <Table cols={cols} rows={pendingRows} indexKey="_id" renderIndexCol={false} dense theme={tableTheme} />
          )}
          {otherRows.length > 0 && (
            <>
              <div className="spacer-xl" />
              <h2>{t('myBookings.pastRequests')}</h2>
              <div className="spacer-s" />
              <Table cols={cols} rows={otherRows} indexKey="_id" renderIndexCol={false} dense theme={tableTheme} />
            </>
          )}
        </>
      )}

      {next && (
        <>
          <div className="spacer-s" />
          <Button variant="secondary" onClick={loadMore} disabled={loadingMore} style={btnSecondaryStyle}>
            {t('common.loadMore')}
          </Button>
        </>
      )}

      {transferRow && (
        <Dialog
          id="transfer-confirm"
          aria-labelledby="transfer-confirm-title"
          isOpen
          close={() => setTransferRow(null)}
          closeButtonLabelText={t('common.close')}
        >
          <Dialog.Header id="transfer-confirm-title" title={t('thingCard.transferConfirmTitle')} />
          <Dialog.Content>
            <p>{t('thingCard.transferConfirmBody')}</p>
            <p style={{ marginBottom: 0 }}>
              <strong>{transferRow._thingHeadline}</strong>
              {transferRow._requesterName
                ? ` — ${t('ownerBookings.requestedBy', { name: transferRow._requesterName })}`
                : ''}
            </p>
          </Dialog.Content>
          <Dialog.ActionButtons>
            <Button
              style={btnStyle}
              disabled={acting === transferRow._code}
              onClick={() => {
                const row = transferRow;
                setTransferRow(null);
                handleAction(row._code, 'accept');
              }}
            >
              {t('thingCard.transferConfirm')}
            </Button>
            <Button variant="secondary" style={btnSecondaryStyle} onClick={() => setTransferRow(null)}>
              {t('common.cancel')}
            </Button>
          </Dialog.ActionButtons>
        </Dialog>
      )}

      <Toast toast={toast} onClose={() => setToast(null)} />
    </PageLayout>
  );
}

import { useEffect, useState } from 'react';
import { useParams, useNavigate, Link } from 'react-router';
import { useTranslation } from 'react-i18next';
import { Button, Notification } from 'hds-react';
import { apiFetch } from '../services/api';
import PageLayout from '../components/PageLayout';
import LoadingSpinner from '../components/LoadingSpinner';
import InlineConfirm from '../components/InlineConfirm';
import ThingTags from '../components/ThingTags';
import ThingInfoRows from '../components/ThingInfoRows';
import OwnerBookingsList from '../components/OwnerBookingsList';
import ThingReportFooter from '../components/ThingReportFooter';
import ThingFaqSection from '../components/ThingFaqSection';
import Toast from '../components/Toast';
import MarkdownText from '../components/MarkdownText';
import ImageCarousel from '../components/ImageCarousel';
import { onImageError } from '../utils/imageFallback';
import { useLocalized } from '../utils/localized';
import useTheeeme from '../hooks/useTheeeme';
import useThingActions from '../hooks/useThingActions';

export default function ThingPage() {
  const { code, thingCode } = useParams();
  const navigate = useNavigate();
  const { t, i18n } = useTranslation();
  const userCode = localStorage.getItem('userCode');
  const isAuthenticated = !!userCode;
  const { tc, btnStyle, btnSecondaryStyle } = useTheeeme();

  const [thing, setThing] = useState(null);
  const [error, setError] = useState('');
  const [toast, setToast] = useState(null);
  // The owner may have written this thing's text once per language.
  const L = useLocalized();
  const headline = L(thing?.headline);
  useEffect(() => {
    document.title = thing ? t('titles.thing', { headline }) : t('titles.thingDefault');
  }, [thing, headline, t]);

  // Anonymous visitor on a PUBLIC collection: like ThingLinkbox's login-to-act
  // mode, show the action buttons but route each click to the collection's join
  // page (they log in there and come back able to act) rather than an inline form.
  const collectionCode = code || thing?.collection_code;
  const loginToAct = !isAuthenticated && !!collectionCode;
  const goJoin = () =>
    navigate(`/collections/${collectionCode}/join`, {
      state: { collectionHeadline: L(thing?.collection_headline) },
    });

  // Owner-button-matrix + reservation view-model (shared with ThingLinkbox).
  const {
    bookingAction,
    bookingActionVerb,
    activating,
    bookings,
    activePendingCode,
    handleRequest,
    handleActivate,
    handleBookingAction,
    isOwner,
    isCollectionOwner,
    isDateBased,
    needsPage,
    canDelete,
    acceptTransfersOwnership,
    hasPendingBookings,
    showButton,
    buttonDisabled,
    loginButtonDisabled,
    buttonLabel,
  } = useThingActions(thing, userCode, {
    canAct: isAuthenticated,
    loginToAct,
    onThingChange: (patch) => setThing((prev) => ({ ...prev, ...patch })),
    setToast,
    activateSuccessMessage: t('thingPage.thingReactivated'),
    collectionCode,
  });

  // The owner "Confirm hold" label, with its in-flight ("Confirming…") state. Shared
  // by the plain accept Button and the ownership-transfer <InlineConfirm> trigger.
  const acceptLabel =
    bookingActionVerb === 'accept' ? t('thingCard.confirming') : t('thingCard.confirmHold');

  // Transfer state
  const [transfers, setTransfers] = useState(null);

  useEffect(() => {
    const controller = new AbortController();
    const { signal } = controller;

    const fetchThing = async () => {
      try {
        const res = await apiFetch(`/api/v1/things/${thingCode}/`, { signal });
        if (res.ok) {
          const data = await res.json();
          if (signal.aborted) return;
          setThing(data);
        } else if (res.status === 403) {
          setError(t('thingPage.noPermission'));
        } else if (res.status === 404) {
          setError(t('thingPage.notFound'));
        } else {
          setError(t('thingPage.errorLoading'));
        }
      } catch {
        if (!signal.aborted) setError(t('common.connectionError'));
      }
    };

    const fetchTransfers = async () => {
      try {
        const res = await apiFetch(`/api/v1/things/${thingCode}/transfers/`, { signal });
        if (res.ok) {
          const data = await res.json();
          if (signal.aborted) return;
          setTransfers(data);
        }
      } catch {
        /* silently fail */
      }
    };

    fetchThing();
    fetchTransfers();
    return () => controller.abort();
  }, [userCode, thingCode, navigate, t]);

  if (error) {
    return (
      <PageLayout title={t('common.error')} backTo="/" backLabel={t('common.home')}>
        <Notification label={t('common.error')} type="error">
          {error}
        </Notification>
      </PageLayout>
    );
  }

  if (!thing) {
    return <LoadingSpinner />;
  }

  // isOwner, type flags, canDelete, showButton, buttonDisabled and
  // buttonLabel all come from useThingActions (destructured at the top).

  const editPath = code
    ? `/collections/${code}/things/${thing.code}/edit`
    : `/things/${thing.code}/edit`;

  const backPath = collectionCode ? `/collections/${collectionCode}` : '/';
  const backLabel =
    L(thing.collection_headline) || (collectionCode ? t('common.collection') : t('common.home'));

  const requestPath = code
    ? `/collections/${code}/things/${thing.code}/request`
    : `/things/${thing.code}/request`;

  const deletePath = code
    ? `/collections/${code}/things/${thing.code}/delete`
    : `/things/${thing.code}/delete`;

  // An empty name in the journey means two different things, and only the
  // viewer's own session tells them apart: for a signed-in reader it is a
  // deleted account (right to erasure), so "Former member" is the truth; for a
  // signed-out one the API withheld every name, and calling people who are
  // still here former members would be a lie the reader has no way to check.
  const holderLabel = (name) =>
    name || t(isAuthenticated ? 'common.formerMember' : 'common.aMember');

  return (
    <PageLayout backTo={backPath} backLabel={backLabel}>
      <div className="form-grid">
        {(() => {
          const images = [thing.thumbnail_url, ...(thing.gallery_urls || [])].filter(Boolean);
          if (images.length === 0) return null;
          if (images.length === 1) {
            return (
              <img
                src={images[0]}
                alt={headline}
                className="detail-image"
                loading="lazy"
                onError={onImageError}
              />
            );
          }
          return <ImageCarousel images={images} alt={headline} />;
        })()}

        <p className="thing-card-meta">
          {new Date(thing.created).toLocaleDateString(i18n.language)}
          {/* Withheld from a reader with no account when the owner is not the
              person who published the collection (see the card's meta line).
              Only that reader gets the generic stand-in: an empty name for a
              signed-in one means the owner never set one, and they are not
              "a member" in the anonymous sense — they are simply unnamed. */}
          {thing.owner_name
            ? ` — ${thing.owner_name}`
            : !isAuthenticated && ` — ${t('common.aMember')}`}
        </p>

        <h1 className="page-title">{headline}</h1>

        {thing.description && <MarkdownText text={L(thing.description)} />}

        <ThingTags thing={thing} isOwner={isOwner} showType={false} />

        <ThingInfoRows thing={thing} isDateBased={isDateBased} />

        {/* Owner bookings list */}
        <OwnerBookingsList
          bookings={bookings}
          activePendingCode={activePendingCode}
          isOwner={isOwner}
        />

        {/* Owner actions */}
        {isOwner && thing.status === 'ACTIVE' && (
          <div className="button-col">
            {needsPage && activePendingCode && (
              <>
                {/* No transfer confirm here, by construction: this branch is
                    `needsPage` (LEND/RENT) and `acceptTransfersOwnership` is its
                    inverse, so the confirm could never render. A loan or rental
                    comes back — nothing changes hands for good. The TAKEN block
                    below is where a GIFT/SELL is accepted, and where the confirm
                    belongs. */}
                <Button
                  fullWidth
                  disabled={!!bookingAction}
                  onClick={() => handleBookingAction('accept')}
                  style={btnStyle}
                >
                  {acceptLabel}
                </Button>
                <Button
                  fullWidth
                  variant="secondary"
                  disabled={!!bookingAction}
                  onClick={() => handleBookingAction('reject')}
                  style={btnSecondaryStyle}
                >
                  {bookingActionVerb === 'reject'
                    ? t('thingCard.cancelling')
                    : t('thingCard.cancelHold')}
                </Button>
              </>
            )}
            <Link to={editPath} style={{ display: 'contents' }}>
              {needsPage && activePendingCode ? (
                <Button fullWidth variant="secondary" style={btnSecondaryStyle}>
                  {t('common.edit')}
                </Button>
              ) : (
                <Button fullWidth style={btnStyle}>
                  {t('common.edit')}
                </Button>
              )}
            </Link>
            {!hasPendingBookings && canDelete && (
              <Button
                fullWidth
                variant="secondary"
                style={btnSecondaryStyle}
                onClick={() => navigate(deletePath, { state: { backPath, backLabel } })}
              >
                {t('common.delete')}
              </Button>
            )}
          </div>
        )}

        {isOwner && thing.status === 'TAKEN' && (
          <div className="button-col">
            {acceptTransfersOwnership ? (
              <InlineConfirm
                triggerLabel={acceptLabel}
                triggerProps={{ fullWidth: true, disabled: !!bookingAction, style: btnStyle }}
                title={t('thingCard.transferConfirmTitle')}
                body={t('thingCard.transferConfirmBody')}
                confirmLabel={t('thingCard.transferConfirm')}
                onConfirm={() => handleBookingAction('accept')}
                confirming={!!bookingAction}
                confirmProps={{ style: btnStyle }}
              />
            ) : (
              <Button
                fullWidth
                disabled={!!bookingAction}
                onClick={() => handleBookingAction('accept')}
                style={btnStyle}
              >
                {acceptLabel}
              </Button>
            )}
            <Button
              fullWidth
              variant="secondary"
              disabled={!!bookingAction}
              onClick={() => handleBookingAction('reject')}
              style={btnSecondaryStyle}
            >
              {bookingActionVerb === 'reject'
                ? t('thingCard.cancelling')
                : t('thingCard.cancelHold')}
            </Button>
            <Link to={editPath} style={{ display: 'contents' }}>
              <Button fullWidth variant="secondary" style={btnSecondaryStyle}>
                {t('common.edit')}
              </Button>
            </Link>
          </div>
        )}

        {isOwner && thing.status === 'INACTIVE' && (
          <div className="button-row">
            <Button
              style={{ ...btnStyle, width: '100%' }}
              disabled={activating}
              onClick={handleActivate}
            >
              {activating ? t('thingCard.reactivating') : t('thingCard.reactivate')}
            </Button>
            <Link to={editPath} style={{ display: 'contents' }}>
              <Button variant="secondary" style={{ ...btnSecondaryStyle, width: '100%' }}>
                {t('common.edit')}
              </Button>
            </Link>
            {canDelete && (
              <Button
                variant="secondary"
                style={{ ...btnSecondaryStyle, width: '100%' }}
                onClick={() => navigate(deletePath, { state: { backPath, backLabel } })}
              >
                {t('common.delete')}
              </Button>
            )}
          </div>
        )}

        {/* Reservation button for invited users. For an anonymous visitor
            (loginToAct) the click routes to the collection's join page. */}
        {showButton && (
          <Button
            fullWidth
            disabled={loginToAct ? loginButtonDisabled : buttonDisabled}
            style={btnStyle}
            onClick={
              loginToAct
                ? goJoin
                : needsPage
                  ? () =>
                      navigate(requestPath, {
                        state: {
                          backPath: code
                            ? `/collections/${code}/things/${thing.code}`
                            : `/things/${thing.code}`,
                          backLabel: headline,
                        },
                      })
                  : handleRequest
            }
          >
            {buttonLabel}
          </Button>
        )}

        {isCollectionOwner && !isOwner && (
          <div className="button-row">
            <Button
              variant="secondary"
              style={{ ...btnSecondaryStyle, width: '100%' }}
              onClick={() => navigate(deletePath, { state: { backPath, backLabel } })}
            >
              {t('common.delete')}
            </Button>
          </div>
        )}

        {/* FAQs Section */}
        <ThingFaqSection
          thingCode={thing.code}
          isOwner={isOwner}
          isAuthenticated={isAuthenticated}
          btnStyle={btnStyle}
          btnSecondaryStyle={btnSecondaryStyle}
          tc={tc}
          onToast={setToast}
        />

        {/* Journey / Transfer history */}
        {transfers && transfers.total_transfers > 0 && (
          <>
            <div className="spacer-m" />
            <hr />
            <div className="spacer-m" />
            <h2>{t('transfers.heading')}</h2>
            <p>{t('transfers.journeyCount', { count: transfers.unique_homes })}</p>
            {transfers.current_holder_name && (
              <p>
                <strong>
                  {t('transfers.currentlyWith', { name: transfers.current_holder_name })}
                </strong>
              </p>
            )}
            <ul className="thing-card-bookings">
              {transfers.transfers.map((tr) => (
                <li key={tr.code}>
                  {holderLabel(tr.from_user_name)} {t('transfers.to')}{' '}
                  {holderLabel(tr.to_user_name)}
                  {' — '}
                  {t('transfers.lentOn', {
                    date: new Date(tr.lent_date).toLocaleDateString(i18n.language),
                  })}
                  {/* `auto_closed` means the daily command wrote this date when
                      the booking's end_date passed — nobody said the thing came
                      back. The journey is the product's most human surface, so
                      it says "due back on" rather than claiming a handover we
                      never witnessed. */}
                  {tr.returned_date && (
                    <>
                      {' '}
                      ·{' '}
                      {t(tr.auto_closed ? 'transfers.dueBackOn' : 'transfers.returnedOn', {
                        date: new Date(tr.returned_date).toLocaleDateString(i18n.language),
                      })}
                    </>
                  )}
                </li>
              ))}
            </ul>
          </>
        )}
        {/* Report footer — logged-in non-owners can flag the listing. */}
        {isAuthenticated && !isOwner && (
          <ThingReportFooter thingCode={thing.code} onToast={setToast} />
        )}
      </div>

      <Toast toast={toast} onClose={() => setToast(null)} />
    </PageLayout>
  );
}

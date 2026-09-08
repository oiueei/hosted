import { useEffect, useState } from 'react';
import { useParams, useNavigate, useLocation } from 'react-router';
import { useTranslation } from 'react-i18next';
import { Button, DateInput, Notification, Select, TextArea } from 'hds-react';
import { DATE_TYPES } from '../constants/things';
import {
  durationLabel,
  isPickupDisabled,
  reservationPickupDisabled,
  isDateBlocked,
  derivedReturnDate,
  isoToDisplay,
  displayToIso,
  DISPLAY_DATE_FORMAT,
} from '../utils/rental';
import { apiFetch } from '../services/api';
import PageLayout from '../components/PageLayout';
import LoadingSpinner from '../components/LoadingSpinner';
import Toast from '../components/Toast';
import useTheeeme from '../hooks/useTheeeme';
import { useLocalized } from '../utils/localized';
import hdsLang from '../utils/hdsLang';

export default function RequestThingPage() {
  const { code, thingCode } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const { t, i18n } = useTranslation();
  const userCode = localStorage.getItem('userCode');
  const { btnStyle, btnSecondaryStyle } = useTheeeme();
  const backPath = location.state?.backPath || '/';
  const backLabel = location.state?.backLabel || t('common.back');

  // Fresh each render — a module-scope `new Date()` would freeze "today" at app
  // load and drift stale past midnight (CODE C18).
  const TODAY = new Date();
  TODAY.setHours(0, 0, 0, 0);
  const MAX_DATE = new Date(TODAY);
  MAX_DATE.setDate(MAX_DATE.getDate() + 90);

  const [thing, setThing] = useState(null);
  const L = useLocalized();
  const headline = L(thing?.headline);
  const isReservation = thing?.type === 'RESERVE_THING';
  useEffect(() => {
    if (!thing) {
      document.title = t('titles.holdDefault');
    } else {
      document.title = isReservation
        ? t('titles.reserveThing', { headline })
        : t('titles.holdThing', { headline });
    }
  }, [thing, headline, isReservation, t]);
  // Date field state lives in the DISPLAY format (DD/MM/YYYY, what the DateInputs
  // emit); it converts to ISO at the consumption boundaries (POST body, derived
  // return date) via displayToIso.
  const [startDate, setStartDate] = useState(isoToDisplay(location.state?.prefillDate) || '');
  const [endDate, setEndDate] = useState('');
  const [duration, setDuration] = useState('');
  const [projectNote, setProjectNote] = useState('');
  const [attempted, setAttempted] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [blockedPeriods, setBlockedPeriods] = useState([]);
  const [toast, setToast] = useState(null);
  const [success, setSuccess] = useState(false);
  // Which thing the load failed for — same reason as the delete pages: a boolean
  // needs clearing at the top of the effect, which is a render spent undoing the
  // previous one.
  const [failedCode, setFailedCode] = useState(null);
  const error = failedCode === thingCode;

  useEffect(() => {
    if (!userCode) return;
    apiFetch(`/api/v1/things/${thingCode}/`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (data) {
          setThing(data);
          setFailedCode(null);
        } else {
          setFailedCode(thingCode);
        }
      })
      .catch(() => setFailedCode(thingCode));
  }, [userCode, thingCode, code]);

  useEffect(() => {
    if (!userCode || !thing || !DATE_TYPES.includes(thing.type)) return;
    apiFetch(`/api/v1/things/${thingCode}/calendar/`)
      .then((res) => (res.ok ? res.json() : []))
      .then((data) => setBlockedPeriods(data))
      .catch(() => {});
  }, [userCode, thingCode, thing]);

  // Per-collection rental rules (#7): a set of fixed lengths + allowed weekdays.
  const rentalDurations = thing?.rental_durations || [];
  const rentalWeekdays = thing?.rental_weekdays || [];
  const isConstrainedRental =
    !!thing && DATE_TYPES.includes(thing.type) && !isReservation && rentalDurations.length > 0;

  // RESERVE: the renter picks a pickup date + a length of 1..reservation_max_days.
  // The Select is omitted (length fixed to 1) when the collection caps it at 1.
  const reservationMax = Math.max(1, thing?.reservation_max_days || 1);
  const reservationLengths = Array.from({ length: reservationMax }, (_, i) => i + 1);

  // With a single fixed length there is nothing to choose, so it *is* the answer
  // until the renter picks otherwise — the pickup picker is usable straight away
  // (#4). Derived rather than written into state once the thing loads: that
  // effect rendered an empty picker, committed it, and only then filled it in,
  // and in between the form's own validation called itself incomplete. What the
  // renter picks always wins; the single option only stands in before they have
  // touched the control.
  const soleDuration = isReservation
    ? reservationMax === 1
      ? '1'
      : ''
    : isConstrainedRental && rentalDurations.length === 1
      ? String(rentalDurations[0])
      : '';
  const chosenDuration = duration || soleDuration;

  // Pickup validity and blocked-date checks are pure, timezone-safe, unit-tested
  // helpers in utils/rental.js; bind them to the current rental state here.
  const pickupDisabled = (date) =>
    isReservation
      ? reservationPickupDisabled(date, {
          rentalWeekdays,
          blockedPeriods,
          duration: chosenDuration,
        })
      : isPickupDisabled(date, { rentalWeekdays, blockedPeriods, duration: chosenDuration });
  const dateBlocked = (date) => isDateBlocked(date, blockedPeriods);

  const handleSubmit = async () => {
    setAttempted(true);

    const isDateBased = thing && DATE_TYPES.includes(thing.type);

    let body = {};
    if (isReservation) {
      // Pickup date + a length of 1..reservation_max_days; the backend derives
      // the end date and auto-confirms.
      const startIso = displayToIso(startDate);
      if (!chosenDuration || !startIso) return;
      body = {
        start_date: startIso,
        duration_days: Number(chosenDuration),
        project_note: projectNote.trim(),
      };
    } else if (isDateBased) {
      if (isConstrainedRental) {
        // Renter picks a fixed length + a pickup date; the return date is derived
        // as pickup + length (a week rental comes back on the same weekday).
        const startIso = displayToIso(startDate);
        if (!chosenDuration || !startIso) return;
        const end = derivedReturnDate(startIso, chosenDuration);
        body = { start_date: startIso, end_date: end };
      } else {
        const startIso = displayToIso(startDate);
        const endIso = displayToIso(endDate);
        if (!startIso || !endIso) return;
        body = { start_date: startIso, end_date: endIso };
      }
    }
    // Pass the collection context so the backend applies that collection's rental
    // rules (harmless for other flows / collections without rules).
    if (code) body.collection_code = code;

    setSubmitting(true);
    setToast(null);
    try {
      const res = await apiFetch(`/api/v1/things/${thingCode}/request/`, {
        method: 'POST',
        body: JSON.stringify(body),
      });
      if (res.ok) {
        setSuccess(true);
      } else if (res.status === 429) {
        setToast({ type: 'error', message: t('common.tooManyAttempts') });
      } else if (res.status === 400) {
        const data = await res.json();
        let message = data.detail;
        if (!message) {
          const errors = Object.values(data).flat();
          message = errors.join(' ') || t('thingPage.invalidRequest');
        }
        setToast({ type: 'error', message });
      } else if (res.status === 409) {
        setToast({ type: 'error', message: t('request.dateOverlap') });
      } else {
        setToast({ type: 'error', message: t('request.errorSending') });
      }
    } catch {
      setToast({ type: 'error', message: t('common.connectionError') });
    } finally {
      setSubmitting(false);
    }
  };

  if (error) {
    return (
      <PageLayout title={t('common.error')} backTo={backPath} backLabel={backLabel}>
        <Notification label={t('thingPage.errorLoading')} type="error" />
      </PageLayout>
    );
  }

  if (!thing) return <LoadingSpinner />;

  const isDateBased = DATE_TYPES.includes(thing.type);

  return (
    <PageLayout
      title={
        isReservation
          ? t('reservation.pageTitle', { headline })
          : t('request.pageTitle', { headline })
      }
      backTo={backPath}
      backLabel={backLabel}
    >
      {success ? (
        <>
          <Notification
            autofocus
            label={isReservation ? t('reservation.successLabel') : t('request.successLabel')}
            type="success"
          >
            {isReservation ? t('reservation.successMessage') : t('request.successMessage')}
          </Notification>
          <div className="spacer-m" />
          <Button
            variant="secondary"
            fullWidth
            onClick={() => navigate(backPath)}
            style={btnSecondaryStyle}
          >
            {t('request.backTo', { label: backLabel })}
          </Button>
        </>
      ) : (
        <>
          {thing.fee && (
            <p>
              <strong>{t('request.priceLabel')}</strong>{' '}
              {t('request.priceValue', { fee: thing.fee })}
            </p>
          )}
          <div className="spacer-m" />
          {isDateBased && (
            <>
              <Notification
                type={thing.available_today ? 'success' : 'info'}
                size="small"
                label={t('thingPage.availabilityLabel')}
              >
                {`${t('thingPage.availabilityLabel')} ${
                  thing.available_today
                    ? t('availability.IMMEDIATE')
                    : thing.next_available
                      ? t('availability.nextAvailable', {
                          date: new Date(thing.next_available).toLocaleDateString(i18n.language, {
                            day: 'numeric',
                            month: 'numeric',
                          }),
                        })
                      : t('availability.noneSoon')
                }`}
              </Notification>
              <div className="spacer-s" />
            </>
          )}
          {isDateBased && isConstrainedRental && (
            <div className="summary-grid section-mt">
              <Select
                id="request-duration"
                texts={{
                  label: t('rental.chooseDuration'),
                  placeholder: t('rental.chooseDurationPlaceholder'),
                  error: attempted && !chosenDuration ? t('rental.durationRequired') : undefined,
                  language: hdsLang(i18n.language),
                }}
                options={rentalDurations.map((d) => ({
                  label: durationLabel(d, t),
                  value: String(d),
                }))}
                value={
                  chosenDuration
                    ? [{ label: durationLabel(Number(chosenDuration), t), value: chosenDuration }]
                    : []
                }
                onChange={(opts) => {
                  setDuration(opts.length ? opts[0].value : '');
                  setStartDate('');
                }}
                invalid={attempted && !chosenDuration}
              />
              <div className="spacer-xxxs" />
              <DateInput
                id="request-pickup-date"
                label={t('rental.pickupLabel')}
                value={startDate}
                onChange={(value) => setStartDate(value)}
                dateFormat={DISPLAY_DATE_FORMAT}
                language="en"
                required
                disabled={!chosenDuration}
                invalid={attempted && !startDate}
                errorText={attempted && !startDate ? t('request.startRequired') : undefined}
                minDate={TODAY}
                maxDate={MAX_DATE}
                dateOutsideRangeErrorText={t('request.dateRange')}
                isDateDisabledBy={pickupDisabled}
                malformedDateErrorText={t('request.dateOverlap')}
              />
              {chosenDuration && displayToIso(startDate) && (
                <p className="thing-card-meta" style={{ marginTop: 'var(--spacing-2-xs)' }}>
                  {t('rental.returnBy', {
                    date: isoToDisplay(derivedReturnDate(displayToIso(startDate), chosenDuration)),
                  })}
                </p>
              )}
            </div>
          )}
          {isReservation && (
            <div className="summary-grid section-mt">
              {reservationMax > 1 && (
                <>
                  <Select
                    id="reservation-duration"
                    texts={{
                      label: t('reservation.durationLabel'),
                      placeholder: t('rental.chooseDurationPlaceholder'),
                      error:
                        attempted && !chosenDuration ? t('rental.durationRequired') : undefined,
                      language: hdsLang(i18n.language),
                    }}
                    options={reservationLengths.map((d) => ({
                      label: t('reservation.days', { count: d }),
                      value: String(d),
                    }))}
                    value={
                      chosenDuration
                        ? [
                            {
                              label: t('reservation.days', { count: Number(chosenDuration) }),
                              value: chosenDuration,
                            },
                          ]
                        : []
                    }
                    onChange={(opts) => {
                      setDuration(opts.length ? opts[0].value : '');
                      setStartDate('');
                    }}
                    invalid={attempted && !chosenDuration}
                  />
                  <div className="spacer-xxxs" />
                </>
              )}
              <DateInput
                id="reservation-pickup-date"
                label={t('reservation.pickupLabel')}
                value={startDate}
                onChange={(value) => setStartDate(value)}
                dateFormat={DISPLAY_DATE_FORMAT}
                language="en"
                required
                disabled={!chosenDuration}
                invalid={attempted && !startDate}
                errorText={attempted && !startDate ? t('request.startRequired') : undefined}
                minDate={TODAY}
                maxDate={MAX_DATE}
                dateOutsideRangeErrorText={t('request.dateRange')}
                isDateDisabledBy={pickupDisabled}
                malformedDateErrorText={t('request.dateOverlap')}
              />
              <div className="spacer-xxxs" />
              <TextArea
                id="reservation-project-note"
                label={t('reservation.projectNoteLabel')}
                helperText={t('reservation.projectNoteHelper', {
                  remaining: 512 - projectNote.length,
                })}
                maxLength={512}
                value={projectNote}
                onChange={(e) => setProjectNote(e.target.value)}
              />
            </div>
          )}
          {isDateBased && !isConstrainedRental && !isReservation && (
            <div className="summary-grid section-mt">
              <DateInput
                id="request-start-date"
                label={t('request.startLabel')}
                value={startDate}
                onChange={(value) => setStartDate(value)}
                dateFormat={DISPLAY_DATE_FORMAT}
                language="en"
                required
                invalid={attempted && !startDate}
                errorText={attempted && !startDate ? t('request.startRequired') : undefined}
                minDate={TODAY}
                maxDate={MAX_DATE}
                dateOutsideRangeErrorText={t('request.dateRange')}
                isDateDisabledBy={dateBlocked}
                malformedDateErrorText={t('request.dateOverlap')}
              />
              <div className="spacer-xxxs" />
              <DateInput
                id="request-end-date"
                label={t('request.endLabel')}
                value={endDate}
                onChange={(value) => setEndDate(value)}
                dateFormat={DISPLAY_DATE_FORMAT}
                language="en"
                required
                invalid={attempted && !endDate}
                errorText={attempted && !endDate ? t('request.endRequired') : undefined}
                minDate={TODAY}
                maxDate={MAX_DATE}
                dateOutsideRangeErrorText={t('request.dateRange')}
                isDateDisabledBy={dateBlocked}
                malformedDateErrorText={t('request.dateOverlap')}
              />
            </div>
          )}

          <div className="spacer-xs" />
          <div className="form-grid">
            <Button fullWidth disabled={submitting} onClick={handleSubmit} style={btnStyle}>
              {submitting
                ? t('common.sending')
                : t(`thingCard.action.${thing?.type}`, { defaultValue: t('thingCard.hold') })}
            </Button>
            <Button
              variant="secondary"
              fullWidth
              onClick={() => navigate(backPath)}
              style={btnSecondaryStyle}
            >
              {t('common.cancel')}
            </Button>
          </div>

          <Toast toast={toast} onClose={() => setToast(null)} />
        </>
      )}
    </PageLayout>
  );
}

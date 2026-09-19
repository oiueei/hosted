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
  formatDate,
  formatRequestedWhen,
  DISPLAY_DATE_FORMAT,
  parseLocalDate,
  parseHM,
  formatHM,
  dayBlocks,
  dayBookings,
  durationOptions,
  freeStartTimes,
  earliestStartMinutes,
  isHourlyPickupDisabled,
} from '../utils/rental';
import { apiFetch, apiErrorMessage, codedErrorMessage } from '../services/api';
import PageLayout from '../components/PageLayout';
import LoadingSpinner from '../components/LoadingSpinner';
import DemoNotice from '../components/DemoNotice';
import MarkdownText from '../components/MarkdownText';
import Toast from '../components/Toast';
import OptionPicker from '../components/OptionPicker';
import { optionPickerFocusId } from '../utils/optionPicker';
import StatusRegion from '../components/StatusRegion';
import useTheeeme from '../hooks/useTheeeme';
import { useLocalized } from '../utils/localized';
import hdsLang from '../utils/hdsLang';
import useCollectionLanguage from '../hooks/useCollectionLanguage';

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
  useCollectionLanguage(thing?.collection_language, [thing?.headline, thing?.description]);
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
  // HOUR-unit reservations only: a duration-option key (its minutes, e.g.
  // '30') and a chosen "HH:MM" start — kept apart from `duration` above
  // (a day-count) since the two are never both meaningful for the same thing.
  const [hourlyDuration, setHourlyDuration] = useState('');
  const [hourlyStartTime, setHourlyStartTime] = useState('');
  const [projectNote, setProjectNote] = useState('');
  const [attempted, setAttempted] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [blockedPeriods, setBlockedPeriods] = useState([]);
  const [toast, setToast] = useState(null);
  const [success, setSuccess] = useState(false);
  // What was actually booked, restated in the success notice — read off the
  // body that went out, so it is the request's own dates, not the form's.
  const [bookedWhen, setBookedWhen] = useState('');
  // RESERVE_THING's "you need to be a member of this group to reserve" (403)
  // can only happen on a PUBLIC collection (can_view already gated everything
  // else, and a non-member reaches it only there), so joining is always
  // genuinely possible — CA's call: don't hand the reader a second button for
  // a step that was never really a choice, just join them (the signed-in half
  // of login-to-act, CollectionPage's own handleJoin) and retry the exact
  // same reservation, transparently, from inside handleSubmit. `notMemberError`
  // (+ the manual "Join this group" fallback button) only ever shows if that
  // auto-join itself fails — a real problem the reader does need to act on.
  const [notMemberError, setNotMemberError] = useState('');
  const [joining, setJoining] = useState(false);
  const [joinError, setJoinError] = useState(false);
  // The group an automatic (or fallback) join just made the reader a member
  // of — said out loud afterwards. Not asking first is CA's call; not telling
  // them at all left someone in a group, its digest and its curator's roster
  // without knowing, above all when the retried reservation then failed.
  const [joinedGroup, setJoinedGroup] = useState('');
  // Which thing the load failed for — same reason as the delete pages: a boolean
  // needs clearing at the top of the effect, which is a render spent undoing the
  // previous one.
  const [failedCode, setFailedCode] = useState(null);
  const error = failedCode === thingCode;

  useEffect(() => {
    if (!userCode) return;
    // In a collection's context, read the thing *through* that collection: its
    // rules (unit, hours, lengths, horizon) and note come back from the same
    // collection the POST below names in `collection_code`, so the form can't
    // show one group's rules while the server applies another's.
    const query = code ? `?collection=${encodeURIComponent(code)}` : '';
    apiFetch(`/api/v1/things/${thingCode}/${query}`)
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
  // Holidays / closures — no handoff (LEND/RENT) or reservation span on one.
  const closedDates = thing?.closed_dates || [];
  const isConstrainedRental =
    !!thing && DATE_TYPES.includes(thing.type) && !isReservation && rentalDurations.length > 0;

  // RESERVE: the renter picks a pickup date + a length of 1..reservation_max_days.
  // The Select is omitted (length fixed to 1) when the collection caps it at 1.
  const reservationMax = Math.max(1, thing?.reservation_max_days || 1);
  const reservationLengths = Array.from({ length: reservationMax }, (_, i) => i + 1);
  // How far ahead a reservation may be booked — the collection's own limit,
  // not the fixed 90 the rental picker uses.
  const reservationMaxDate = new Date(TODAY);
  reservationMaxDate.setDate(
    reservationMaxDate.getDate() + (thing?.reservation_horizon_days || 90)
  );

  // HOUR-unit RESERVE: day → duration → start time, in that order (unlike the
  // DAY-unit flow above, which picks the length first). Each step's options
  // depend on the previous one, computed fresh from the thing's opening_hours
  // and the fetched calendar — the same pure helpers the backend's own
  // Collection.day_opening_blocks / reservation_hour_violation mirror.
  const isHourlyReservation = isReservation && thing?.reservation_unit === 'HOUR';
  const openingHours = thing?.opening_hours || {};
  const reservationMinMinutes = thing?.reservation_min_minutes || 60;
  const reservationMaxMinutes = thing?.reservation_max_minutes || 180;
  const hourlyPickupDisabled = (date) =>
    isHourlyPickupDisabled(date, {
      openingHours,
      closedDates,
      blockedPeriods,
      minMinutes: reservationMinMinutes,
    });
  const selectedIso = displayToIso(startDate);
  const blocksForSelectedDay =
    isHourlyReservation && selectedIso ? dayBlocks(openingHours, parseLocalDate(selectedIso)) : [];
  const bookingsForSelectedDay =
    isHourlyReservation && selectedIso
      ? dayBookings(blockedPeriods, selectedIso)
      : { wholeDay: false, ranges: [] };
  const hourlyDurationChoices = isHourlyReservation
    ? durationOptions(reservationMinMinutes, reservationMaxMinutes)
    : [];
  const chosenDurationOption = hourlyDurationChoices.find((o) => o.key === hourlyDuration);
  // For today, only starts not yet passed (by the browser's clock) — see
  // `earliestStartMinutes`. Recomputed every render, so a start that passes
  // while the page sits open drops out of the list...
  const hourlyStartTimeChoices = chosenDurationOption
    ? freeStartTimes(
        blocksForSelectedDay,
        chosenDurationOption.minutes,
        bookingsForSelectedDay,
        reservationMinMinutes,
        earliestStartMinutes(selectedIso)
      )
    : [];
  // ...and out of the selection too: a start the reader picked before it
  // passed is no longer one this page will send.
  const chosenStartTime = hourlyStartTimeChoices.includes(hourlyStartTime) ? hourlyStartTime : '';
  // What a Reserve click on the HOUR flow is still missing, once a day is
  // picked (a missing day is the DateInput's own error). No start time is only
  // "missing" when there were some to choose from — with none, the "no start
  // times" notice already says to pick a shorter duration.
  const hourlyDurationMissing = isHourlyReservation && !!selectedIso && !chosenDurationOption;
  const hourlyStartTimeMissing =
    isHourlyReservation &&
    !!chosenDurationOption &&
    hourlyStartTimeChoices.length > 0 &&
    !chosenStartTime;
  const durationOptionLabel = (opt) => {
    const hours = Math.floor(opt.minutes / 60);
    const minutes = opt.minutes % 60;
    if (hours === 0) return t('reservation.minutes', { count: minutes });
    if (minutes === 0) return t('reservation.hours', { count: hours });
    return t('reservation.hoursAndMinutes', { hours, minutes });
  };
  // Radios for a handful, a dropdown past OptionPicker's RADIO_MAX — a short
  // minimum turns both lists long (48 start times at 15 minutes over 12 hours).
  const durationPickerOptions = hourlyDurationChoices.map((opt) => ({
    value: opt.key,
    label: durationOptionLabel(opt),
  }));
  const startTimePickerOptions = hourlyStartTimeChoices.map((hm) => ({ value: hm, label: hm }));

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
          closedDates,
        })
      : isPickupDisabled(date, {
          rentalWeekdays,
          blockedPeriods,
          duration: chosenDuration,
          closedDates,
        });
  const dateBlocked = (date) => isDateBlocked(date, blockedPeriods, closedDates);

  // The request body, built fresh from current form state — `null` when a
  // required field is still empty. A function, not a one-off inline block, so
  // both the normal submit and the manual "Join this group" fallback (a
  // *separate* click, its own later render) build it the same way — the
  // fallback used to replay whatever body the earlier failed attempt had
  // captured, which could book a date the reader had since changed on screen.
  const buildReservationBody = () => {
    const isDateBased = thing && DATE_TYPES.includes(thing.type);
    let body = null;
    if (isReservation && isHourlyReservation) {
      // Pickup date + a chosen slot; the backend derives end_date = start + 1
      // and auto-confirms.
      const startIso = displayToIso(startDate);
      if (!startIso || !chosenDurationOption || !chosenStartTime) return null;
      const endTime = formatHM(parseHM(chosenStartTime) + chosenDurationOption.minutes);
      body = {
        start_date: startIso,
        start_time: chosenStartTime,
        end_time: endTime,
        project_note: projectNote.trim(),
      };
    } else if (isReservation) {
      // Pickup date + a length of 1..reservation_max_days; the backend derives
      // the end date and auto-confirms.
      const startIso = displayToIso(startDate);
      if (!chosenDuration || !startIso) return null;
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
        if (!chosenDuration || !startIso) return null;
        const end = derivedReturnDate(startIso, chosenDuration);
        body = { start_date: startIso, end_date: end };
      } else {
        const startIso = displayToIso(startDate);
        const endIso = displayToIso(endDate);
        if (!startIso || !endIso) return null;
        body = { start_date: startIso, end_date: endIso };
      }
    }
    // Pass the collection context so the backend applies that collection's
    // rental rules (harmless for other flows / collections without rules).
    if (body && code) body.collection_code = code;
    return body;
  };

  // Shared by the first attempt's non-403 branches and the retry after an
  // auto-join below — a business-rule failure reads the same either way.
  const showRequestError = async (res) => {
    if (res.status === 429) {
      setToast({ type: 'error', message: t('common.tooManyAttempts') });
    } else if (res.status === 400) {
      // A rule refusal comes coded and is said in the reader's language
      // (apiErrorMessage); anything else is the server's own text.
      const data = await res.json();
      setToast({ type: 'error', message: apiErrorMessage(data) || t('thingPage.invalidRequest') });
    } else if (res.status === 403) {
      const data = await res.json();
      setToast({ type: 'error', message: apiErrorMessage(data) || t('request.errorSending') });
    } else if (res.status === 409) {
      // "That time is already taken" for an hourly slot, "those dates"
      // otherwise — and this page's own copy for anything uncoded.
      const data = await res.json().catch(() => null);
      setToast({ type: 'error', message: codedErrorMessage(data) || t('request.dateOverlap') });
    } else {
      setToast({ type: 'error', message: t('request.errorSending') });
    }
  };

  // The one collection an automatic join may ever target: the one the server
  // resolved this thing to (`thing.collection_code`, read through
  // `?collection=` on the collection-context route) — never the route's `code`
  // on its own. The route is whatever link the reader followed, and nothing
  // checks it names a collection this thing lives in: joining it as written
  // let a link like `/collections/<someone's PUBLIC group>/things/<a real
  // space>/request` join the reader to that group on one Reserve click, and
  // hand its curator their email address in the roster (found in the
  // 2026-09-18 security round). When the route names a collection the server
  // didn't resolve to, there is no join at all — the reason is shown instead.
  const joinableCollection = () => {
    const resolved = thing?.collection_code;
    if (!resolved || (code && code !== resolved)) return null;
    return resolved;
  };

  // The signed-in half of login-to-act (CollectionPage's own handleJoin,
  // reused): a PUBLIC collection's own member roster is one POST away for
  // someone who already has an account.
  //
  // Only ever called for the backend's `code: "not_a_member"` marker (see
  // handleSubmit), which can only fire on a PUBLIC collection — can_view
  // already gated everything else, and a non-member reaches it only there —
  // so joining is always genuinely possible. Membership was never really a
  // choice being offered, so it isn't asked for: join, then retry the
  // reservation, transparently (CA's call). `notMemberError` + the manual
  // fallback button only ever show if this auto-join itself fails.
  const joinThenRetry = async (body, fallbackMessage) => {
    const collectionCode = joinableCollection();
    if (!collectionCode) {
      setNotMemberError(fallbackMessage || t('request.errorSending'));
      return;
    }
    setJoining(true);
    setJoinError(false);
    try {
      let joinRes;
      try {
        joinRes = await apiFetch(`/api/v1/collections/${collectionCode}/join/`, {
          method: 'POST',
        });
      } catch {
        joinRes = null;
      }
      if (!joinRes?.ok) {
        setJoinError(true);
        setNotMemberError(fallbackMessage || t('request.errorSending'));
        return;
      }
      setNotMemberError('');
      // `joinableCollection` is `thing.collection_code`, so this headline is
      // the group that was just joined.
      setJoinedGroup(L(thing?.collection_headline) || '');
      try {
        const retryRes = await apiFetch(`/api/v1/things/${thingCode}/request/`, {
          method: 'POST',
          body: JSON.stringify(body),
        });
        if (retryRes.ok) {
          setBookedWhen(formatRequestedWhen(body));
          setSuccess(true);
        } else {
          await showRequestError(retryRes);
        }
      } catch {
        setToast({ type: 'error', message: t('common.connectionError') });
      }
    } finally {
      setJoining(false);
    }
  };

  // A Reserve click that can't be sent used to do nothing visible on the HOUR
  // flow: the radio groups had no error state, unlike the DAY flow's Select
  // (found in review, 2026-09-18 — and more reachable once a start that passes
  // while the page sits open drops out of the selection on its own). The group
  // now shows HDS's error text, and focus moves to its first option, which
  // reads the question out — HDS links that error text to nothing.
  const focusMissingHourlyChoice = () => {
    const first = hourlyDurationMissing
      ? optionPickerFocusId('reservation-duration', durationPickerOptions)
      : hourlyStartTimeMissing
        ? optionPickerFocusId('reservation-start-time', startTimePickerOptions)
        : null;
    if (first) document.getElementById(first)?.focus();
  };

  const handleSubmit = async () => {
    setAttempted(true);
    const body = buildReservationBody();
    if (!body) {
      focusMissingHourlyChoice();
      return;
    }

    setSubmitting(true);
    setToast(null);
    setNotMemberError('');
    try {
      const res = await apiFetch(`/api/v1/things/${thingCode}/request/`, {
        method: 'POST',
        body: JSON.stringify(body),
      });
      if (res.ok) {
        setBookedWhen(formatRequestedWhen(body));
        setSuccess(true);
      } else if (res.status === 403) {
        // Only this specific marker means "not a member" — any *other* 403
        // (e.g. the thing going INACTIVE while this form was open) must not
        // be mistaken for it and silently join the reader to a group over an
        // unrelated error. And only when there is a collection it is safe to
        // join (`joinableCollection`, above).
        const data = await res.json();
        if (isReservation && data.code === 'not_a_member' && joinableCollection()) {
          await joinThenRetry(body, apiErrorMessage(data));
        } else {
          setToast({ type: 'error', message: apiErrorMessage(data) || t('request.errorSending') });
        }
      } else {
        await showRequestError(res);
      }
    } catch {
      setToast({ type: 'error', message: t('common.connectionError') });
    } finally {
      setSubmitting(false);
    }
  };

  // The manual fallback — shown only when the automatic join above itself
  // failed. Rebuilds the body fresh rather than replaying the failed
  // attempt's — the reader may well have changed the date while this was
  // showing, and a fixed old body would confirm the wrong one.
  const handleJoinGroup = () => {
    const body = buildReservationBody();
    if (!body) {
      setAttempted(true);
      return;
    }
    return joinThenRetry(body, notMemberError);
  };

  // The optional project note — the same field in the DAY and HOUR flows, one
  // or the other on screen, never both (their ids stay distinct anyway).
  const projectNoteField = (id) => (
    <TextArea
      id={id}
      label={t('reservation.projectNoteLabel')}
      helperText={t('reservation.projectNoteHelper', { remaining: 512 - projectNote.length })}
      maxLength={512}
      value={projectNote}
      onChange={(e) => setProjectNote(e.target.value)}
    />
  );

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
      description={
        thing.collection_request_info ? (
          <MarkdownText text={L(thing.collection_request_info)} />
        ) : undefined
      }
      backTo={backPath}
      backLabel={backLabel}
    >
      {thing.collection_is_onboarding && <DemoNotice />}
      {notMemberError && (
        <div className="invite-nudge" role="alert">
          <p style={{ margin: 0 }}>{notMemberError}</p>
          <div style={{ marginTop: 'var(--spacing-xs)' }}>
            <Button style={btnStyle} disabled={joining} onClick={handleJoinGroup}>
              {joining ? t('joinToAct.joining') : t('collectionPage.visitorJoin')}
            </Button>
          </div>
          {joinError && (
            <p role="alert" style={{ color: 'var(--color-error)', marginBottom: 0 }}>
              {t('collectionPage.visitorJoinError')}
            </p>
          )}
        </div>
      )}
      {/* The join stands even when the retried reservation fails (the slot
          was taken meanwhile, say), and then there is no success message to
          carry it — so it has a notice of its own. Rendered unconditionally,
          the condition inside: see StatusRegion.jsx. */}
      <StatusRegion>
        {joinedGroup && !success && (
          <Notification type="info" label={t('reservation.joinedLabel')}>
            {t('reservation.joinedGroup', { group: joinedGroup })}
          </Notification>
        )}
      </StatusRegion>
      {success ? (
        <>
          <Notification
            autofocus
            label={isReservation ? t('reservation.successLabel') : t('request.successLabel')}
            type="success"
          >
            {isReservation ? t('reservation.successMessage') : t('request.successMessage')}
            {/* What and when, said back: a reservation confirms on the spot,
                with no owner step to catch a wrong day or hour. */}
            {bookedWhen && (
              <p style={{ margin: 'var(--spacing-2-xs) 0 0' }}>
                <strong>{headline}</strong>
                <br />
                {bookedWhen}
              </p>
            )}
            {joinedGroup && (
              <p style={{ margin: 'var(--spacing-2-xs) 0 0' }}>
                {t('reservation.joinedGroup', { group: joinedGroup })}
              </p>
            )}
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
                notificationAriaLabel={t('thingPage.availabilityLabel')}
              >
                {thing.available_today
                  ? t('availability.IMMEDIATE')
                  : thing.next_available
                    ? t('availability.nextAvailable', { date: formatDate(thing.next_available) })
                    : t('availability.noneSoon')}
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
                language={hdsLang(i18n.language)}
                openButtonAriaLabel={t('datePicker.open')}
                selectButtonLabel={t('datePicker.select')}
                closeButtonLabel={t('datePicker.close')}
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
          {isReservation && !isHourlyReservation && (
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
                helperText={t('reservation.pickupHelper')}
                value={startDate}
                onChange={(value) => setStartDate(value)}
                dateFormat={DISPLAY_DATE_FORMAT}
                language={hdsLang(i18n.language)}
                openButtonAriaLabel={t('datePicker.open')}
                selectButtonLabel={t('datePicker.select')}
                closeButtonLabel={t('datePicker.close')}
                required
                disabled={!chosenDuration}
                invalid={attempted && !startDate}
                errorText={attempted && !startDate ? t('request.startRequired') : undefined}
                minDate={TODAY}
                maxDate={reservationMaxDate}
                dateOutsideRangeErrorText={t('reservation.dateRange', {
                  days: thing.reservation_horizon_days || 90,
                })}
                isDateDisabledBy={pickupDisabled}
                malformedDateErrorText={t('request.dateOverlap')}
              />
              {/* The span the member is about to book, once both parts are set
                  — the reservation auto-confirms, so there is no owner step
                  that would catch a wrong end date. Shown only when the length
                  is more than a day (a 1-day slot IS the pickup date). */}
              {Number(chosenDuration) > 1 && displayToIso(startDate) && (
                <p className="thing-card-meta" style={{ marginTop: 'var(--spacing-2-xs)' }}>
                  {t('reservation.dateSummary', {
                    start: startDate,
                    end: isoToDisplay(
                      derivedReturnDate(displayToIso(startDate), Number(chosenDuration) - 1)
                    ),
                  })}
                </p>
              )}
              <div className="spacer-xxxs" />
              {projectNoteField('reservation-project-note')}
            </div>
          )}
          {isReservation && isHourlyReservation && (
            <div className="summary-grid section-mt">
              <DateInput
                id="reservation-pickup-date-hourly"
                label={t('reservation.pickupLabelHourly')}
                helperText={t('reservation.pickupHelperHourly')}
                value={startDate}
                onChange={(value) => {
                  setStartDate(value);
                  setHourlyDuration('');
                  setHourlyStartTime('');
                }}
                dateFormat={DISPLAY_DATE_FORMAT}
                language={hdsLang(i18n.language)}
                openButtonAriaLabel={t('datePicker.open')}
                selectButtonLabel={t('datePicker.select')}
                closeButtonLabel={t('datePicker.close')}
                required
                invalid={attempted && !startDate}
                errorText={attempted && !startDate ? t('request.startRequired') : undefined}
                minDate={TODAY}
                maxDate={reservationMaxDate}
                dateOutsideRangeErrorText={t('reservation.dateRange', {
                  days: thing.reservation_horizon_days || 90,
                })}
                isDateDisabledBy={hourlyPickupDisabled}
                malformedDateErrorText={t('request.dateOverlap')}
              />
              {selectedIso && (
                <>
                  <div className="spacer-xxxs" />
                  <OptionPicker
                    idPrefix="reservation-duration"
                    name="reservation-duration"
                    label={t('reservation.durationLabelHourly')}
                    placeholder={t('rental.chooseDurationPlaceholder')}
                    options={durationPickerOptions}
                    value={hourlyDuration}
                    onChange={(key) => {
                      setHourlyDuration(key);
                      setHourlyStartTime('');
                    }}
                    errorText={
                      attempted && hourlyDurationMissing ? t('rental.durationRequired') : undefined
                    }
                  />
                </>
              )}
              {hourlyDuration && hourlyStartTimeChoices.length > 0 && (
                <>
                  <div className="spacer-xxxs" />
                  <OptionPicker
                    idPrefix="reservation-start-time"
                    name="reservation-start-time"
                    label={t('reservation.startTimeLabel')}
                    placeholder={t('reservation.startTimePlaceholder')}
                    options={startTimePickerOptions}
                    value={chosenStartTime}
                    onChange={setHourlyStartTime}
                    errorText={
                      attempted && hourlyStartTimeMissing
                        ? t('reservation.startTimeRequired')
                        : undefined
                    }
                  />
                </>
              )}
              {/* Rendered unconditionally (StatusRegion), the conditional stays
                  inside it — see StatusRegion.jsx's own note. A live region
                  only announces a change made *inside a region that already
                  existed*: gating the Notification itself behind `hourlyDuration`
                  (as this used to) meant the reader picking a duration with no
                  free start left that day heard nothing at all — the
                  Notification was never inside a live region, since it didn't
                  exist yet either (WCAG 4.1.3, found in review 2026-09-18). */}
              <StatusRegion>
                {/* The slot this Reserve will book, once all three parts are
                    picked — the end time is never shown anywhere else, and the
                    reservation auto-confirms. In the live region, so choosing a
                    start time reads the whole slot back. */}
                {selectedIso && chosenDurationOption && chosenStartTime && (
                  <p className="thing-card-meta" style={{ marginTop: 'var(--spacing-2-xs)' }}>
                    {t('reservation.slotSummary', {
                      date: isoToDisplay(selectedIso),
                      start: chosenStartTime,
                      end: formatHM(parseHM(chosenStartTime) + chosenDurationOption.minutes),
                    })}
                  </p>
                )}
                {hourlyDuration && hourlyStartTimeChoices.length === 0 && (
                  <>
                    <div className="spacer-xxxs" />
                    {/* `notificationAriaLabel` distinguishes this landmark from
                        the availability Notification above, which is always
                        mounted alongside it here — two HDS Notifications share
                        the same default aria-label ("Notification"), which
                        axe's landmark-unique rule (correctly) flags once both
                        are on screen at once (found by the new axe coverage
                        for this page, 2026-09-18). */}
                    <Notification
                      type="info"
                      size="small"
                      label={t('reservation.noStartTimesLabel')}
                      notificationAriaLabel={t('reservation.noStartTimesLabel')}
                    >
                      {t('reservation.noStartTimesForDuration')}
                    </Notification>
                  </>
                )}
              </StatusRegion>
              <div className="spacer-xxxs" />
              {projectNoteField('reservation-project-note-hourly')}
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
                language={hdsLang(i18n.language)}
                openButtonAriaLabel={t('datePicker.open')}
                selectButtonLabel={t('datePicker.select')}
                closeButtonLabel={t('datePicker.close')}
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
                language={hdsLang(i18n.language)}
                openButtonAriaLabel={t('datePicker.open')}
                selectButtonLabel={t('datePicker.select')}
                closeButtonLabel={t('datePicker.close')}
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

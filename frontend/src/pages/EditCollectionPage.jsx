import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router';
import { useTranslation } from 'react-i18next';
import { TextInput, TextArea, Select, Button, Notification, Accordion } from 'hds-react';
import { apiFetch, extractApiError } from '../services/api';
import PageLayout from '../components/PageLayout';
import CollectionForm from '../components/CollectionForm';
import CollectionModeField from '../components/CollectionModeField';
import downloadBlob, { filenameFromResponse } from '../utils/downloadBlob';
import useCapabilities, { isOfferable } from '../hooks/useCapabilities';
import RentalRulesFields from '../components/RentalRulesFields';
import ReservationRulesFields from '../components/ReservationRulesFields';
import ClosedDatesField from '../components/ClosedDatesField';
import ImageUpload from '../components/ImageUpload';
import PdfUpload from '../components/PdfUpload';
import { SUPPORTED_LANGUAGES } from '../i18n';
import TagInput from '../components/TagInput';
import LocalizedInfo from '../components/LocalizedInfo';
import LoadingSpinner from '../components/LoadingSpinner';
import Toast from '../components/Toast';
import useTheeeme from '../hooks/useTheeeme';
import { useLocalized, localizedCounter } from '../utils/localized';
import { closedDatesToDisplay } from '../utils/rental';
import hdsLang from '../utils/hdsLang';
import StatusRegion from '../components/StatusRegion';

export default function EditCollectionPage() {
  const { t, i18n } = useTranslation();
  // The form holds the raw value (the owner edits the map itself); only the
  // page title and the back label show the resolved words.
  const L = useLocalized();
  const { code } = useParams();
  const navigate = useNavigate();
  const userCode = localStorage.getItem('userCode');
  const { tc, btnStyle, btnSecondaryStyle } = useTheeeme();
  const [loading, setLoading] = useState(true);
  const [headline, setHeadline] = useState('');
  useEffect(() => {
    document.title = headline
      ? t('titles.editCollection', { headline: L(headline) })
      : t('titles.editCollectionDefault');
  }, [headline, t, L]);
  const [description, setDescription] = useState('');
  const [status, setStatus] = useState('ACTIVE');
  const [mode, setMode] = useState('PROPRIETARY');
  // The mode as the server has it, which is **not** `mode` once the user starts
  // picking. It is what `isOfferable` needs: the server judges only a *change*,
  // so the stored mode is always submittable, while the one currently selected
  // in the form carries no such promise. Keying the filter on `mode` made a
  // withheld-but-stored option vanish the moment anything else was clicked,
  // stranding the owner on a form that could no longer express what they had.
  const [savedMode, setSavedMode] = useState(null);
  const [visibility, setVisibility] = useState('PRIVATE');
  const [allowProposals, setAllowProposals] = useState(true);
  const [digestFrequency, setDigestFrequency] = useState('NONE');
  const [allowedThingTypes, setAllowedThingTypes] = useState([]);
  const [rentalDurations, setRentalDurations] = useState([]);
  const [rentalWeekdays, setRentalWeekdays] = useState([]);
  const [reservationMaxDays, setReservationMaxDays] = useState(1);
  const [reservationHorizonDays, setReservationHorizonDays] = useState(90);
  const [closedDates, setClosedDates] = useState('');
  const [homePage, setHomePage] = useState('');
  const [depositPolicy, setDepositPolicy] = useState('');
  const [tags, setTags] = useState([]);
  const [thumbnail, setThumbnail] = useState('');
  const [thumbnailUrl, setThumbnailUrl] = useState('');
  const [language, setLanguage] = useState('');
  const [welcomeDoc, setWelcomeDoc] = useState('');
  const [welcomeDocUrl, setWelcomeDocUrl] = useState('');
  const [pauseMessage, setPauseMessage] = useState('');
  const [isPaused, setIsPaused] = useState(false);
  // The one control on this page still stricter than "the server enforces
  // it": deleting the collection is deliberately not a co-owner power, and
  // the button isn't worth showing to someone the server would refuse.
  // Everything else here (save, pause, stats, export) already carries no
  // client-side gate at all — a co-owner reaching this page saves exactly
  // as the founder would, no change needed.
  const [ownerCode, setOwnerCode] = useState(null);
  const isOwner = userCode === ownerCode;
  const [pauseSubmitting, setPauseSubmitting] = useState(false);
  const [statsError, setStatsError] = useState(false);
  const [collectionExportError, setCollectionExportError] = useState(null);
  const [collectionExportDownloading, setCollectionExportDownloading] = useState(false);
  const [calendarError, setCalendarError] = useState(null);
  const [calendarInfo, setCalendarInfo] = useState(null);
  const [calendarDownloading, setCalendarDownloading] = useState(false);
  const [errors, setErrors] = useState({});
  const [submitting, setSubmitting] = useState(false);
  const [submitAttempted, setSubmitAttempted] = useState(false);
  const [toast, setToast] = useState(null);

  const STATUS_OPTIONS = [
    { label: t('editCollection.statusActive'), value: 'ACTIVE' },
    { label: t('editCollection.statusInactive'), value: 'INACTIVE' },
  ];

  const ALL_MODE_OPTIONS = [
    {
      label: t('editCollection.modeProprietary'),
      description: t('createCollection.modeProprietaryDesc'),
      value: 'PROPRIETARY',
    },
    {
      label: t('editCollection.modeCommunity'),
      description: t('createCollection.modeCommunityDesc'),
      value: 'COMMUNITY',
    },
  ];
  // `savedMode` — not `mode` — is the current value here: a collection opened
  // before this deployment narrowed still shows the mode it is in, and keeps
  // showing it while the owner tries the alternatives. The server only judges a
  // change; a form that hid the stored answer would submit a wrong one.
  const capabilities = useCapabilities();
  const isReservations = allowedThingTypes.length === 1 && allowedThingTypes[0] === 'RESERVE_THING';
  const MODE_OPTIONS = ALL_MODE_OPTIONS.filter(
    (opt) =>
      isOfferable(capabilities, 'collection_modes', opt.value, savedMode) &&
      !(isReservations && opt.value !== 'PROPRIETARY')
  );

  const DIGEST_OPTIONS = [
    { label: t('editCollection.digestNone'), value: 'NONE' },
    { label: t('editCollection.digestWeekly'), value: 'WEEKLY' },
    { label: t('editCollection.digestMonthly'), value: 'MONTHLY' },
  ];

  // Live "pick at least one" feedback once a submit has been attempted (P1-5).
  const allowedTypesError =
    submitAttempted && allowedThingTypes.length === 0
      ? t('createCollection.allowedTypesAtLeastOne')
      : '';

  const handleModeChange = (newMode) => {
    if (newMode === mode) return;
    setMode(newMode);
    // Both modes allow the same types, so the selection carries over untouched.
  };

  const handleTypesChange = (types) => {
    setAllowedThingTypes(types);
    if (types.length === 1 && types[0] === 'RESERVE_THING' && mode !== 'PROPRIETARY') {
      setMode('PROPRIETARY');
    }
  };

  useEffect(() => {
    const fetchData = async () => {
      try {
        const collectionRes = await apiFetch(`/api/v1/collections/${code}/`);

        if (collectionRes.ok) {
          const data = await collectionRes.json();
          setOwnerCode(data.owner || null);
          setHeadline(data.headline || '');
          setDescription(data.description || '');
          setStatus(data.status || 'ACTIVE');
          setMode(data.mode || 'PROPRIETARY');
          setSavedMode(data.mode || 'PROPRIETARY');
          setVisibility(data.visibility || 'PRIVATE');
          // `?? true` rather than `||`: the field is a boolean, and a genuine
          // `false` (the owner turned recommendations off) must survive the load
          // instead of springing back on at the next save.
          setAllowProposals(data.allow_member_proposals ?? true);
          setDigestFrequency(data.digest_frequency || 'NONE');
          setAllowedThingTypes(data.allowed_thing_types || []);
          setRentalDurations(data.rental_durations || []);
          setRentalWeekdays(data.rental_weekdays || []);
          setReservationMaxDays(data.reservation_max_days || 1);
          setReservationHorizonDays(data.reservation_horizon_days || 90);
          setClosedDates(closedDatesToDisplay(data.closed_dates));
          setHomePage(data.home_page || '');
          setDepositPolicy(data.deposit_policy || '');
          setTags(data.tags || []);
          setThumbnail(data.thumbnail || '');
          setThumbnailUrl(data.thumbnail_url || '');
          // Blank = inherit the deployment default; the members' own preference
          // still wins over whatever the owner picks here.
          setLanguage(data.language || i18n.resolvedLanguage || i18n.language);
          setWelcomeDoc(data.welcome_doc || '');
          setWelcomeDocUrl(data.welcome_doc_url || '');
          setPauseMessage(data.pause_message || '');
          setIsPaused(data.is_paused || false);
        } else {
          setToast({ type: 'error', message: t('editCollection.errorLoading') });
        }
      } catch {
        setToast({ type: 'error', message: t('common.connectionError') });
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [userCode, code, navigate, t, i18n]);

  const validate = () => {
    setSubmitAttempted(true);
    const newErrors = {};
    if (!headline.trim()) newErrors.headline = t('editCollection.titleRequired');
    if (localizedCounter(headline, 64).over) newErrors.headline = t('editCollection.maxHeadline');
    if (localizedCounter(description, 2000).over)
      newErrors.description = t('editCollection.maxDescription');
    setErrors(newErrors);
    const allowedTypesOk = allowedThingTypes.length > 0;
    return Object.keys(newErrors).length === 0 && allowedTypesOk;
  };

  const handleSubmit = async () => {
    if (!validate()) return;
    setSubmitting(true);
    setToast(null);

    const body = {
      headline: headline.trim(),
      description: description.trim(),
      status,
      mode,
      visibility,
      allow_member_proposals: allowProposals,
      digest_frequency: digestFrequency,
      allowed_thing_types: allowedThingTypes,
      rental_durations: isReservations ? [] : rentalDurations,
      rental_weekdays: rentalWeekdays,
      closed_dates: closedDates,
      home_page: homePage.trim(),
      deposit_policy: isReservations ? '' : depositPolicy.trim(),
      tags,
      thumbnail: thumbnail || '',
      language,
      welcome_doc: welcomeDoc || '',
    };
    if (isReservations) {
      body.reservation_max_days = reservationMaxDays;
      body.reservation_horizon_days = reservationHorizonDays;
    }

    try {
      const res = await apiFetch(`/api/v1/collections/${code}/`, {
        method: 'PATCH',
        body: JSON.stringify(body),
      });
      if (res.ok) {
        navigate(`/collections/${code}`);
      } else if (res.status === 429) {
        setToast({ type: 'error', message: t('common.tooManyAttempts') });
      } else if (res.status === 400) {
        // Surface the backend's own message — it names the offending types when
        // narrowing would orphan things, the bad token / far-future date when
        // `closed_dates` is rejected, etc. — so the owner can act on it.
        const message = await extractApiError(res);
        setToast({ type: 'error', message: message || t('editCollection.errorSaving') });
      } else {
        setToast({ type: 'error', message: t('editCollection.errorSaving') });
      }
    } catch {
      setToast({ type: 'error', message: t('common.connectionError') });
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return <LoadingSpinner />;
  }

  const handlePauseToggle = async () => {
    setPauseSubmitting(true);
    setToast(null);
    const newMessage = isPaused ? '' : pauseMessage.trim();
    try {
      const res = await apiFetch(`/api/v1/collections/${code}/`, {
        method: 'PATCH',
        body: JSON.stringify({ pause_message: newMessage }),
      });
      if (res.ok) {
        setIsPaused(!isPaused);
        if (isPaused) setPauseMessage('');
        setToast({ type: 'success', message: isPaused ? t('pause.resumed') : t('pause.paused') });
      } else {
        setToast({ type: 'error', message: t('common.error') });
      }
    } catch {
      setToast({ type: 'error', message: t('common.connectionError') });
    } finally {
      setPauseSubmitting(false);
    }
  };

  const handleDownloadStats = async () => {
    setStatsError(false);
    try {
      const res = await apiFetch(`/api/v1/collections/${code}/stats/`);
      if (!res.ok) throw new Error('stats');
      downloadBlob(await res.blob(), `${code}-stats.csv`);
    } catch {
      setStatsError(true);
    }
  };

  const handleDownloadCalendar = async () => {
    setCalendarError(null);
    setCalendarInfo(null);
    setCalendarDownloading(true);
    try {
      const res = await apiFetch(`/api/v1/collections/${code}/calendar-export/`, {
        method: 'POST',
      });
      if (res.ok) {
        // The server counts the events it put in the file; 0 means everything
        // was already exported, so there is nothing to hand the browser.
        const count = Number(res.headers.get('X-Calendar-Events') || '0');
        if (count > 0) {
          downloadBlob(await res.blob(), `${code}-calendar.csv`);
          setCalendarInfo(t('calendarExport.done', { count }));
        } else {
          setCalendarInfo(t('calendarExport.nothingNew'));
        }
      } else if (res.status === 429) {
        setCalendarError(t('common.tooManyAttempts'));
      } else {
        setCalendarError(t('calendarExport.error'));
      }
    } catch {
      setCalendarError(t('common.connectionError'));
    } finally {
      setCalendarDownloading(false);
    }
  };

  const handleDownloadCollectionExport = async () => {
    setCollectionExportError(null);
    setCollectionExportDownloading(true);
    try {
      const res = await apiFetch(`/api/v1/collections/${code}/export/`);
      if (res.ok) {
        downloadBlob(await res.blob(), filenameFromResponse(res, `${code}.json`));
      } else if (res.status === 429) {
        setCollectionExportError(t('common.tooManyAttempts'));
      } else {
        setCollectionExportError(t('collectionExport.error'));
      }
    } catch {
      setCollectionExportError(t('common.connectionError'));
    } finally {
      setCollectionExportDownloading(false);
    }
  };

  return (
    <PageLayout backTo={`/collections/${code}`} backLabel={L(headline) || t('common.collection')}>
      <h1 className="page-title-xl">{t('editCollection.pageTitle')}</h1>
      <div className="form-grid">
        <TextInput
          id="edit-collection-headline"
          label={t('editCollection.titleLabel')}
          value={headline}
          onChange={(e) => setHeadline(e.target.value)}
          required
          invalid={!!errors.headline}
          errorText={errors.headline}
          helperText={localizedCounter(headline, 64).text}
        />
        <TextArea
          id="edit-collection-description"
          label={t('editCollection.descriptionLabel')}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          invalid={!!errors.description}
          errorText={errors.description}
          helperText={localizedCounter(description, 2000).text}
        />
        <LocalizedInfo id="edit-collection-localized-info" />
        <Select
          id="edit-collection-status"
          texts={{ label: t('editCollection.statusLabel'), language: hdsLang(i18n.language) }}
          helper={t('editCollection.statusHelper')}
          options={STATUS_OPTIONS}
          value={status}
          onChange={(selectedOptions) => {
            if (selectedOptions.length > 0) {
              setStatus(selectedOptions[0].value);
            }
          }}
        />
        <CollectionModeField
          idPrefix="edit-collection"
          label={t('editCollection.modeLabel')}
          options={MODE_OPTIONS}
          catalogue={ALL_MODE_OPTIONS}
          value={mode}
          onChange={handleModeChange}
        />
        <CollectionForm
          idPrefix="edit-collection"
          allowedThingTypes={allowedThingTypes}
          setAllowedThingTypes={handleTypesChange}
          mode={mode}
          visibility={visibility}
          setVisibility={setVisibility}
          allowProposals={allowProposals}
          setAllowProposals={setAllowProposals}
          errors={{ ...errors, allowedThingTypes: allowedTypesError }}
          theeemeColor01={tc.color_01}
        />
      </div>
      {/* Everything optional, with a safe default, folds away so the happy path
          (title, status, mode, who can add) reads at a glance (DESIGN §3, O1). */}
      <Accordion
        heading={t('createCollection.advancedTitle')}
        language="en"
        headingLevel={2}
        theme={tc.color_04 ? { '--header-color': `var(--color-${tc.color_04})` } : undefined}
      >
        <div className="form-grid">
          <div>
            <TagInput
              tags={tags}
              onChange={setTags}
              label={t('createCollection.tagsLabel')}
              placeholder={t('createCollection.tagsPlaceholder')}
              helperText={t('createCollection.tagsHelper')}
            />
            <LocalizedInfo id="edit-collection-tags-info" variant="tags" />
          </div>
          {isReservations ? (
            <ReservationRulesFields
              idPrefix="edit-collection"
              reservationMaxDays={reservationMaxDays}
              setReservationMaxDays={setReservationMaxDays}
              reservationHorizonDays={reservationHorizonDays}
              setReservationHorizonDays={setReservationHorizonDays}
              rentalWeekdays={rentalWeekdays}
              setRentalWeekdays={setRentalWeekdays}
              theeemeColor01={tc.color_01}
            />
          ) : (
            <RentalRulesFields
              idPrefix="edit-collection"
              rentalDurations={rentalDurations}
              setRentalDurations={setRentalDurations}
              rentalWeekdays={rentalWeekdays}
              setRentalWeekdays={setRentalWeekdays}
              depositPolicy={depositPolicy}
              setDepositPolicy={setDepositPolicy}
              theeemeColor01={tc.color_01}
            />
          )}
          <ClosedDatesField
            id="edit-collection-closed-dates"
            value={closedDates}
            onChange={setClosedDates}
          />
          <TextInput
            id="edit-collection-home-page"
            type="url"
            label={t('homePage.label')}
            helperText={t('homePage.helper')}
            placeholder="https://…"
            value={homePage}
            onChange={(e) => setHomePage(e.target.value)}
            maxLength={128}
          />
          <Select
            id="edit-collection-digest"
            texts={{ label: t('editCollection.digestLabel'), language: hdsLang(i18n.language) }}
            helper={t('editCollection.digestHelper')}
            options={DIGEST_OPTIONS}
            value={digestFrequency}
            onChange={(selectedOptions) => {
              if (selectedOptions.length > 0) {
                setDigestFrequency(selectedOptions[0].value);
              }
            }}
          />
          <Select
            id="edit-collection-language"
            texts={{ label: t('collectionLanguage.label'), language: hdsLang(i18n.language) }}
            helper={t('collectionLanguage.helper')}
            options={SUPPORTED_LANGUAGES.map((l) => ({ label: l.name, value: l.code }))}
            value={language}
            onChange={(selectedOptions) => {
              if (selectedOptions.length > 0) {
                setLanguage(selectedOptions[0].value);
              }
            }}
          />
          <ImageUpload
            id="edit-collection-thumbnail"
            label={t('upload.thumbnailLabel')}
            value={thumbnail}
            onChange={setThumbnail}
            currentUrl={thumbnailUrl}
            folder="oiueei/collections"
          />
          <PdfUpload
            id="edit-collection-welcome-doc"
            label={t('upload.welcomeDocLabel')}
            onChange={setWelcomeDoc}
            currentUrl={welcomeDocUrl}
            helperText={t('upload.welcomeDocHelper')}
          />
        </div>
      </Accordion>
      <div className="form-actions">
        <Button disabled={submitting} onClick={handleSubmit} style={{ ...btnStyle, width: '100%' }}>
          {submitting ? t('common.saving') : t('common.save')}
        </Button>
        {isOwner && (
          <Button
            variant="secondary"
            fullWidth
            disabled={submitting}
            onClick={() => {
              navigate(`/collections/${code}/delete`, {
                state: {
                  backPath: `/collections/${code}/edit`,
                  backLabel: L(headline) || t('common.collection'),
                },
              });
            }}
            style={{
              '--background-color': 'var(--color-white)',
              '--border-color': tc.color_01 ? `var(--color-${tc.color_01})` : undefined,
              '--color': tc.color_04 ? `var(--color-${tc.color_04})` : undefined,
              '--background-color-hover': tc.color_01 ? `var(--color-${tc.color_01})` : undefined,
              '--color-hover': tc.color_06 ? `var(--color-${tc.color_06})` : 'var(--color-white)',
              marginTop: 'var(--spacing-s)',
            }}
          >
            {t('common.delete')}
          </Button>
        )}
      </div>
      <div
        style={{
          marginTop: 'var(--spacing-xl)',
          borderTop: '1px solid var(--color-black-20)',
          paddingTop: 'var(--spacing-m)',
        }}
      >
        <h2>{t('pause.sectionHeading')}</h2>
        <p>{t('pause.sectionHelper')}</p>
        {!isPaused && (
          <div className="form-grid">
            <TextArea
              id="pause-message"
              label={t('pause.messageLabel')}
              helperText={`${pauseMessage.length}/256 — ${t('pause.messageHelper')}`}
              value={pauseMessage}
              onChange={(e) => setPauseMessage(e.target.value)}
              maxLength={256}
            />
          </div>
        )}
        {isPaused && (
          <blockquote
            style={{
              borderLeft: `4px solid ${tc.color_01 ? `var(--color-${tc.color_01})` : 'var(--color-black-50)'}`,
              paddingLeft: 'var(--spacing-m)',
              margin: 'var(--spacing-m) 0',
              fontStyle: 'italic',
            }}
          >
            {pauseMessage}
          </blockquote>
        )}
        {!isPaused && !pauseMessage.trim() && (
          <p
            style={{
              marginTop: 'var(--spacing-s)',
              fontSize: 'var(--fontsize-body-s)',
              color: 'var(--color-black-60)',
            }}
          >
            {t('pause.messageRequiredHint')}
          </p>
        )}
        <div style={{ marginTop: 'var(--spacing-m)' }}>
          <Button
            variant="secondary"
            fullWidth
            disabled={pauseSubmitting || (!isPaused && !pauseMessage.trim())}
            onClick={handlePauseToggle}
            style={btnSecondaryStyle}
          >
            {pauseSubmitting
              ? isPaused
                ? t('pause.resuming')
                : t('pause.pausing')
              : isPaused
                ? t('pause.resumeButton')
                : t('pause.pauseButton')}
          </Button>
        </div>
      </div>
      <div
        style={{
          marginTop: 'var(--spacing-xl)',
          borderTop: '1px solid var(--color-black-20)',
          paddingTop: 'var(--spacing-m)',
        }}
      >
        <Button
          variant="secondary"
          fullWidth
          onClick={handleDownloadStats}
          style={btnSecondaryStyle}
        >
          {t('stats.downloadStats')}
        </Button>
        <StatusRegion>
          {statsError && (
            <Notification type="error" size="small" style={{ marginTop: 'var(--spacing-xs)' }}>
              {t('stats.downloadStatsError')}
            </Notification>
          )}
        </StatusRegion>
        {/* The whole group, not the summary above — a different download, so the
            label and the copy beside it have to say so: it carries other
            members' data, and whoever downloads it is who answers for it. */}
        <div style={{ marginTop: 'var(--spacing-s)' }}>
          <Button
            variant="secondary"
            fullWidth
            disabled={collectionExportDownloading}
            onClick={handleDownloadCollectionExport}
            style={btnSecondaryStyle}
          >
            {collectionExportDownloading
              ? t('collectionExport.downloading')
              : t('collectionExport.downloadButton')}
          </Button>
          <p
            style={{
              marginTop: 'var(--spacing-2-xs)',
              fontSize: 'var(--fontsize-body-s)',
              color: 'var(--color-black-60)',
            }}
          >
            {t('collectionExport.notice')}
          </p>
          <StatusRegion>
            {collectionExportError && (
              <Notification type="error" size="small" style={{ marginTop: 'var(--spacing-xs)' }}>
                {collectionExportError}
              </Notification>
            )}
          </StatusRegion>
        </div>
        {/* The calendar CSV — only the date-based reservations (loans, rentals,
            on-site reservations), and only the ones added since the last
            download, so importing it twice never doubles the calendar. */}
        <div style={{ marginTop: 'var(--spacing-s)' }}>
          <Button
            variant="secondary"
            fullWidth
            disabled={calendarDownloading}
            onClick={handleDownloadCalendar}
            style={btnSecondaryStyle}
          >
            {calendarDownloading
              ? t('calendarExport.downloading')
              : t('calendarExport.downloadButton')}
          </Button>
          <p
            style={{
              marginTop: 'var(--spacing-2-xs)',
              fontSize: 'var(--fontsize-body-s)',
              color: 'var(--color-black-60)',
            }}
          >
            {t('calendarExport.notice')}
          </p>
          <StatusRegion>
            {calendarError && (
              <Notification type="error" size="small" style={{ marginTop: 'var(--spacing-xs)' }}>
                {calendarError}
              </Notification>
            )}
            {calendarInfo && (
              <Notification type="success" size="small" style={{ marginTop: 'var(--spacing-xs)' }}>
                {calendarInfo}
              </Notification>
            )}
          </StatusRegion>
        </div>
      </div>
      <Toast toast={toast} onClose={() => setToast(null)} />
    </PageLayout>
  );
}

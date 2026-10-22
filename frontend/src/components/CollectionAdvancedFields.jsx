import { TextInput, TextArea, Select, Accordion } from 'hds-react';
import { useTranslation } from 'react-i18next';
import RentalRulesFields from './RentalRulesFields';
import ReservationRulesFields from './ReservationRulesFields';
import ClosedDatesField from './ClosedDatesField';
import ImageUpload from './ImageUpload';
import PdfUpload from './PdfUpload';
import TagInput from './TagInput';
import LocalizedInfo from './LocalizedInfo';
import { SUPPORTED_LANGUAGES } from '../i18n';
import { localizedCounter, localizedHelper } from '../utils/localized';
import hdsLang from '../utils/hdsLang';

/**
 * The "More options" block of the create and edit forms of a collection: everything
 * optional, with a safe default, folded away so the happy path (title, mode, who can
 * add) reads at a glance (DESIGN §3). The two pages hold the state — each loads and
 * submits it its own way — and hand it down; this is only the form, so the two
 * cannot drift.
 *
 * What differs is handed in, not branched on here:
 * - `idPrefix` (`create-collection` / `edit-collection`) names every field's id;
 * - `colors` are the viewer's theeeme tokens;
 * - `thumbnailUrl` / `welcomeDocUrl` are the saved files Edit shows (Create has none);
 * - `afterEmailNote` is a slot under the email note (Edit's "send me a test email").
 *
 * `reservationRules` / `rentalRules` are the props of `ReservationRulesFields` /
 * `RentalRulesFields` apart from the id prefix and the colours, which this adds.
 * `isReservations` (a shed) picks the first, `hasRequestPage` (a library or a shed)
 * the second and the fields that only the request page uses: closed days and the
 * note shown before someone asks.
 */
export default function CollectionAdvancedFields({
  idPrefix,
  colors,
  isReservations,
  hasRequestPage,
  tags,
  setTags,
  reservationRules,
  rentalRules,
  closedDates,
  setClosedDates,
  requestInfo,
  setRequestInfo,
  emailNote,
  setEmailNote,
  afterEmailNote = null,
  homePage,
  setHomePage,
  digestFrequency,
  setDigestFrequency,
  language,
  setLanguage,
  thumbnail,
  setThumbnail,
  thumbnailUrl,
  setWelcomeDoc,
  welcomeDocUrl,
}) {
  const { t, i18n } = useTranslation();
  const requestInfoCount = localizedCounter(requestInfo, 512);
  const emailNoteCount = localizedCounter(emailNote, 512);

  const digestOptions = [
    { label: t('editCollection.digestNone'), value: 'NONE' },
    { label: t('editCollection.digestWeekly'), value: 'WEEKLY' },
    { label: t('editCollection.digestMonthly'), value: 'MONTHLY' },
  ];

  return (
    <Accordion
      heading={t('createCollection.advancedTitle')}
      language={hdsLang(i18n.language)}
      headingLevel={2}
      theme={colors.color_04 ? { '--header-color': `var(--color-${colors.color_04})` } : undefined}
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
          <LocalizedInfo id={`${idPrefix}-tags-info`} variant="tags" />
        </div>
        {isReservations ? (
          <ReservationRulesFields
            idPrefix={idPrefix}
            {...reservationRules}
            theeemeColor01={colors.color_01}
            theeemeColor06={colors.color_06}
          />
        ) : hasRequestPage ? (
          <RentalRulesFields
            idPrefix={idPrefix}
            {...rentalRules}
            theeemeColor01={colors.color_01}
            theeemeColor06={colors.color_06}
          />
        ) : null}
        {hasRequestPage && (
          <ClosedDatesField
            id={`${idPrefix}-closed-dates`}
            value={closedDates}
            onChange={setClosedDates}
          />
        )}
        {hasRequestPage && (
          <div>
            <p className="weekday-field-helper">{t('requestInfo.helper')}</p>
            <TextArea
              id={`${idPrefix}-request-info`}
              label={t('requestInfo.label')}
              value={requestInfo}
              onChange={(e) => setRequestInfo(e.target.value)}
              invalid={requestInfoCount.over}
              errorText={requestInfoCount.over ? t('requestInfo.maxLength') : undefined}
              helperText={localizedHelper(requestInfo, 512, t)}
            />
            <LocalizedInfo id={`${idPrefix}-request-info-info`} variant="requestInfo" />
          </div>
        )}
        <div>
          <p className="weekday-field-helper">{t('emailNote.helper')}</p>
          <TextArea
            id={`${idPrefix}-email-note`}
            label={t('emailNote.label')}
            value={emailNote}
            onChange={(e) => setEmailNote(e.target.value)}
            invalid={emailNoteCount.over}
            errorText={emailNoteCount.over ? t('emailNote.maxLength') : undefined}
            helperText={localizedHelper(emailNote, 512, t)}
          />
          <LocalizedInfo id={`${idPrefix}-email-note-info`} variant="emailNote" />
          {afterEmailNote}
        </div>
        <TextInput
          id={`${idPrefix}-home-page`}
          type="url"
          label={t('homePage.label')}
          helperText={t('homePage.helper')}
          placeholder="https://…"
          value={homePage}
          onChange={(e) => setHomePage(e.target.value)}
          maxLength={128}
        />
        <Select
          id={`${idPrefix}-digest`}
          texts={{
            label: t('editCollection.digestLabel'),
            assistive: t('editCollection.digestHelper'),
            language: hdsLang(i18n.language),
          }}
          options={digestOptions}
          value={digestFrequency}
          onChange={(selectedOptions) => {
            if (selectedOptions.length > 0) setDigestFrequency(selectedOptions[0].value);
          }}
        />
        <Select
          id={`${idPrefix}-language`}
          texts={{
            label: t('collectionLanguage.label'),
            assistive: t('collectionLanguage.helper'),
            language: hdsLang(i18n.language),
          }}
          options={SUPPORTED_LANGUAGES.map((l) => ({ label: l.name, value: l.code }))}
          value={language}
          onChange={(selectedOptions) => {
            if (selectedOptions.length > 0) setLanguage(selectedOptions[0].value);
          }}
        />
        <ImageUpload
          id={`${idPrefix}-thumbnail`}
          label={t('upload.thumbnailLabel')}
          value={thumbnail}
          onChange={setThumbnail}
          currentUrl={thumbnailUrl}
          folder="oiueei/collections"
        />
        <PdfUpload
          id={`${idPrefix}-welcome-doc`}
          label={t('upload.welcomeDocLabel')}
          onChange={setWelcomeDoc}
          currentUrl={welcomeDocUrl}
          helperText={t('upload.welcomeDocHelper')}
        />
      </div>
    </Accordion>
  );
}

import { useCallback, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button, Notification } from 'hds-react';
import { apiFetch } from '../services/api';
import downloadBlob, { filenameFromResponse } from '../utils/downloadBlob';
import StatusRegion from './StatusRegion';

/**
 * The "Download reservations for your calendar" control, shared by the two
 * places a curator meets it: the foot of `EditCollectionPage` (where it was
 * born, between the other admin downloads) and the hero of `CollectionPage` —
 * a curator managing the group can take its schedule with them without
 * walking into the settings first.
 *
 * `useCalendarExport(code)` owns the whole request, so the two call sites
 * cannot drift: the **POST** (kept for contract stability with the backend —
 * the call used to mutate, marking reservations delivered; it no longer does,
 * since 2026-09-28 the file is an .ics carrying every upcoming reservation
 * every time, deduped on re-import by a stable per-booking UID), the count in
 * the `X-Calendar-Events` header (0 downloads nothing and says why), the
 * server-set `Content-Disposition` filename, and the three failure shapes
 * (429 / anything else / a thrown request). The page calls it once and hands
 * the result to both halves:
 *
 *     const calendarExport = useCalendarExport(code);
 *     <CalendarExportButton calendar={calendarExport} style={btnSecondaryStyle} />
 *     <CalendarExportStatus calendar={calendarExport} />
 *
 * Button and status are separate components so the hero's `button-row-wide`
 * holds only buttons (the row turns into a column on phones) while the
 * outcome message lands underneath it — and the `StatusRegion` still
 * pre-dates its content, which is what makes a screen reader announce it.
 */
// The hook stays co-located with the two components it feeds — the page calls
// it once and hands the same state object to button and status, so splitting
// it into hooks/ would separate one contract across two directories.
// eslint-disable-next-line react-refresh/only-export-components -- the hook owns the state the two components below render
export function useCalendarExport(code) {
  const { t } = useTranslation();
  const [error, setError] = useState(null);
  const [info, setInfo] = useState(null);
  const [downloading, setDownloading] = useState(false);

  const download = useCallback(async () => {
    setError(null);
    setInfo(null);
    setDownloading(true);
    try {
      const res = await apiFetch(`/api/v1/collections/${code}/calendar-export/`, {
        method: 'POST',
      });
      if (res.ok) {
        // The server counts the events the file holds; 0 means there are no
        // upcoming reservations at all, so there is nothing to hand the browser.
        const count = Number(res.headers.get('X-Calendar-Events') || '0');
        if (count > 0) {
          // The server-set name, with the literal as fallback — the same rule
          // the collection export follows, so the two downloads cannot drift
          // apart the day the server changes one.
          downloadBlob(await res.blob(), filenameFromResponse(res, `${code}-calendar.ics`));
          setInfo(t('calendarExport.done', { count }));
        } else {
          setInfo(t('calendarExport.nothingNew'));
        }
      } else if (res.status === 429) {
        setError(t('common.tooManyAttempts'));
      } else {
        setError(t('calendarExport.error'));
      }
    } catch {
      setError(t('common.connectionError'));
    } finally {
      setDownloading(false);
    }
  }, [code, t]);

  return { error, info, downloading, download };
}

export default function CalendarExportButton({ calendar, style, fullWidth }) {
  const { t } = useTranslation();
  return (
    <Button
      variant="secondary"
      fullWidth={fullWidth}
      disabled={calendar.downloading}
      onClick={calendar.download}
      style={style}
    >
      {calendar.downloading ? t('calendarExport.downloading') : t('calendarExport.downloadButton')}
    </Button>
  );
}

export function CalendarExportStatus({ calendar }) {
  return (
    <StatusRegion>
      {calendar.error && (
        <Notification type="error" size="small" style={{ marginTop: 'var(--spacing-xs)' }}>
          {calendar.error}
        </Notification>
      )}
      {calendar.info && (
        <Notification type="success" size="small" style={{ marginTop: 'var(--spacing-xs)' }}>
          {calendar.info}
        </Notification>
      )}
    </StatusRegion>
  );
}

import { useCallback, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { apiFetch } from '../services/api';
import downloadBlob, { filenameFromResponse } from '../utils/downloadBlob';

/**
 * The calendar download's request and outcome, behind the collection menu's
 * "Download the calendar (ICS)" entry (`useCollectionDownloads` calls it and
 * hands the state to the menu and to the status zone). It used to share a
 * button component with the foot of `EditCollectionPage`; both went when the
 * downloads moved into the menu (2026-10-03), and the hook alone is what is left.
 *
 * It owns the whole request, so nothing else has to know it: the **POST**
 * (kept for contract stability with the backend — the call used to mutate,
 * marking reservations delivered; it no longer does, since 2026-09-28 the file
 * is an .ics carrying every upcoming reservation every time, deduped on
 * re-import by a stable per-booking UID), the counts in the
 * `X-Calendar-Events` / `X-Calendar-Cancelled` headers (both 0 downloads
 * nothing and says why — a file of cancellations alone is still downloaded,
 * since importing it is what takes them off a calendar), the
 * server-set `Content-Disposition` filename, and the three failure shapes
 * (429 / anything else / a thrown request). Returns
 * `{ error, info, downloading, download }`.
 */
export default function useCalendarExport(code) {
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
        // The server counts what the file holds: confirmed events, and the
        // cancellations that take earlier imports back off a calendar. Both 0
        // means there is nothing to hand the browser.
        const count = Number(res.headers.get('X-Calendar-Events') || '0');
        const cancelled = Number(res.headers.get('X-Calendar-Cancelled') || '0');
        if (count > 0 || cancelled > 0) {
          // The server-set name, with the literal as fallback — the same rule
          // the collection export follows, so the two downloads cannot drift
          // apart the day the server changes one.
          downloadBlob(await res.blob(), filenameFromResponse(res, `${code}-calendar.ics`));
          if (count === 0) {
            setInfo(t('calendarExport.doneOnlyCancelled', { count: cancelled }));
          } else if (cancelled > 0) {
            setInfo(
              `${t('calendarExport.done', { count })} ${t('calendarExport.alsoCancelled', { count: cancelled })}`
            );
          } else {
            setInfo(t('calendarExport.done', { count }));
          }
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

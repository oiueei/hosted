import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button, Notification } from 'hds-react';
import { apiFetch } from '../services/api';
import PageLayout from '../components/PageLayout';
import downloadBlob, { filenameFromResponse } from '../utils/downloadBlob';

// Mirrors export_service.build_account_export's top-level keys, in the order
// the manifest lists them — this is what "what you take" actually is, not a
// paraphrase of it.
const TAKE_KEYS = [
  'profile',
  'collectionsOwned',
  'collectionsMemberOf',
  'things',
  'bookings',
  'faqs',
  'proposals',
  'transfers',
  'notifications',
  'reports',
  'activity',
];

// The 8 points EXPORT_TOOL.md specifies, restated as page copy — the same
// content the downloaded file's own `_readme` carries, so a reader who never
// opens the JSON still learns exactly what it withholds and why.
const DONT_TAKE_KEYS = [
  'credentials',
  'othersData',
  'othersThings',
  'reports',
  'photos',
  'emails',
  'logs',
  'deleted',
];

/**
 * `/me/data` — self-service data portability (GDPR art. 20).
 *
 * The mirror of DeleteAccountPage: states what the download carries and what
 * it deliberately leaves out, then a single button. No confirmation step here
 * — unlike erasure, downloading a copy is reversible by construction (you can
 * always ask again, up to the rate limit) and takes nothing away from anyone.
 */
export default function DataExportPage() {
  const { t } = useTranslation();
  useEffect(() => {
    document.title = t('titles.dataExport');
  }, [t]);
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState('');

  const handleDownload = async () => {
    setDownloading(true);
    setError('');
    try {
      const res = await apiFetch('/api/v1/auth/export/');
      if (res.ok) {
        downloadBlob(await res.blob(), filenameFromResponse(res, 'oiueei-my-data.json'));
      } else if (res.status === 429) {
        setError(t('common.tooManyAttempts'));
      } else {
        setError(t('dataExport.error'));
      }
    } catch {
      setError(t('common.connectionError'));
    } finally {
      setDownloading(false);
    }
  };

  return (
    <PageLayout
      title={t('dataExport.pageTitle')}
      backTo="/me/edit"
      backLabel={t('editProfile.pageTitle')}
      description={t('dataExport.intro')}
    >
      <div style={{ maxWidth: '600px' }}>
        <h2>{t('dataExport.whatYouTakeTitle')}</h2>
        <ul>
          {TAKE_KEYS.map((key) => (
            <li key={key}>{t(`dataExport.take.${key}`)}</li>
          ))}
        </ul>
        <div className="spacer-m" />
        <h2>{t('dataExport.whatYouDontTakeTitle')}</h2>
        <ol>
          {DONT_TAKE_KEYS.map((key) => (
            <li key={key}>{t(`dataExport.dontTake.${key}`)}</li>
          ))}
        </ol>
        <div className="spacer-m" />
        {error && (
          <Notification
            label={t('common.error')}
            type="error"
            style={{ marginBottom: 'var(--spacing-s)' }}
          >
            {error}
          </Notification>
        )}
        <Button disabled={downloading} onClick={handleDownload}>
          {downloading ? t('dataExport.downloading') : t('dataExport.downloadButton')}
        </Button>
      </div>
    </PageLayout>
  );
}

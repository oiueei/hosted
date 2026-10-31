import { useEffect, useState } from 'react';
import { useParams, useNavigate, useLocation } from 'react-router';
import { useTranslation } from 'react-i18next';
import { Button, Notification, IconTrash } from 'hds-react';
import { apiFetch } from '../services/api';
import PageLayout from '../components/PageLayout';
import LoadingSpinner from '../components/LoadingSpinner';
import Toast from '../components/Toast';
import useTheeeme from '../hooks/useTheeeme';
import useCollectionTheeeme from '../hooks/useCollectionTheeeme';
import { useLocalized } from '../utils/localized';
import useCollectionLanguage from '../hooks/useCollectionLanguage';
import useDocumentTitle from '../hooks/useDocumentTitle';

export default function DeleteThingPage() {
  const { t } = useTranslation();
  // Owner content (headlines, tags) may carry one text per language.
  const L = useLocalized();
  const { thingCode } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const userCode = localStorage.getItem('userCode');
  const { btnStyle, btnSecondaryStyle } = useTheeeme();
  const backPath = location.state?.backPath || '/';
  const backLabel = location.state?.backLabel || t('common.back');

  const [thing, setThing] = useState(null);
  const [deleting, setDeleting] = useState(false);
  const [toast, setToast] = useState(null);
  // Which thing the load failed for — see DeleteCollectionPage: a boolean needs
  // clearing at the top of the effect, and that reset is a setState in an effect
  // body. Tying the failure to its code needs no reset at all.
  const [failedCode, setFailedCode] = useState(null);
  const error = failedCode === thingCode;
  useCollectionLanguage(thing?.collection_language, [thing?.headline, thing?.description]);
  useCollectionTheeeme(thing?.collection_theeeme_colors, thing?.collection_koro);

  useDocumentTitle(
    thing
      ? t('titles.deleteThing', { headline: L(thing.headline) })
      : t('titles.deleteThingDefault')
  );

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
  }, [userCode, thingCode]);

  const handleDelete = async () => {
    setDeleting(true);
    setToast(null);
    try {
      const res = await apiFetch(`/api/v1/things/${thingCode}/`, { method: 'DELETE' });
      if (res.ok || res.status === 204) {
        navigate(backPath);
      } else {
        setToast({ type: 'error', message: t('deleteThing.errorDeleting') });
      }
    } catch {
      setToast({ type: 'error', message: t('common.connectionError') });
    } finally {
      setDeleting(false);
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

  return (
    <PageLayout
      title={t('deleteThing.pageTitle', { headline: L(thing.headline) })}
      backTo={backPath}
      backLabel={backLabel}
    >
      {/* Same erasure map as DeleteCollectionPage and DeleteAccountPage. A thing
          is not only the owner's: other people asked questions on it and it may
          have a journey behind it, and both go with it (FAQ and ThingTransfer
          cascade on the FK). Someone's pending hold dies here too. "This action
          cannot be undone" said none of that. */}
      <p>
        <strong>{t('deleteThing.warning')}</strong>
      </p>
      <div className="spacer-s" />
      <p>{t('deleteThing.whatGoesTitle')}</p>
      <ul className="measure">
        <li>{t('deleteThing.goesPhotos')}</li>
        <li>{t('deleteThing.goesFaq')}</li>
        <li>{t('deleteThing.goesHolds')}</li>
      </ul>
      {/* How many people the deletion will email: those with a pending or accepted
          request on this thing. The server counts them for whoever may delete it. */}
      {thing.live_requesters_count > 0 && (
        <p data-testid="live-requesters">
          {t('deleteThing.liveRequesters', { count: thing.live_requesters_count })}
        </p>
      )}
      <div className="spacer-s" />
      <div className="form-grid">
        <Button
          fullWidth
          disabled={deleting}
          onClick={handleDelete}
          style={btnStyle}
          iconStart={<IconTrash aria-hidden="true" />}
        >
          {deleting ? t('common.deleting') : t('common.delete')}
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
    </PageLayout>
  );
}

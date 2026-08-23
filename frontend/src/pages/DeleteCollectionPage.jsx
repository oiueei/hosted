import { useEffect, useState } from 'react';
import { useParams, useNavigate, useLocation } from 'react-router';
import { useTranslation } from 'react-i18next';
import { Button, Notification, IconTrash } from 'hds-react';
import { apiFetch } from '../services/api';
import PageLayout from '../components/PageLayout';
import LoadingSpinner from '../components/LoadingSpinner';
import Toast from '../components/Toast';
import useTheeeme from '../hooks/useTheeeme';
import { useLocalized } from '../utils/localized';

export default function DeleteCollectionPage() {
  const { t } = useTranslation();
  // Owner content (headlines, tags) may carry one text per language.
  const L = useLocalized();
  const { code } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const userCode = localStorage.getItem('userCode');
  const { btnStyle, btnSecondaryStyle } = useTheeeme();
  const backPath = location.state?.backPath || `/collections/${code}/edit`;
  const backLabel = location.state?.backLabel || t('common.back');

  const [collection, setCollection] = useState(null);
  const [deleting, setDeleting] = useState(false);
  const [toast, setToast] = useState(null);
  // Which collection the load failed for, rather than a bare boolean. The effect
  // below re-runs when the route's code changes, and a boolean had to be cleared
  // synchronously at the top of it so the previous collection's failure did not
  // sit over the new one — a setState in an effect body, and a render spent
  // undoing the last one. Derived, there is nothing to clear: a failure about a
  // code you are no longer on simply stops being true.
  const [failedCode, setFailedCode] = useState(null);
  const error = failedCode === code;

  useEffect(() => {
    document.title = collection
      ? t('titles.deleteCollection', { headline: L(collection.headline) })
      : t('titles.deleteCollectionDefault');
  }, [collection, t, L]);

  useEffect(() => {
    if (!userCode) return;
    apiFetch(`/api/v1/collections/${code}/`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (data) {
          setCollection(data);
          setFailedCode(null);
        } else {
          setFailedCode(code);
        }
      })
      .catch(() => setFailedCode(code));
  }, [userCode, code]);

  const handleDelete = async () => {
    setDeleting(true);
    setToast(null);
    try {
      const res = await apiFetch(`/api/v1/collections/${code}/`, { method: 'DELETE' });
      if (res.ok || res.status === 204) {
        navigate('/');
      } else {
        setToast({ type: 'error', message: t('deleteCollection.errorDeleting') });
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
        <Notification label={t('collectionPage.errorLoading')} type="error" />
      </PageLayout>
    );
  }

  if (!collection) return <LoadingSpinner />;

  return (
    <PageLayout
      title={t('deleteCollection.pageTitle', { headline: L(collection.headline) })}
      backTo={backPath}
      backLabel={backLabel}
    >
      {/* The erasure map, to the standard DeleteAccountPage set. A COMMUNITY
          collection holds things its members contributed, and deleting it takes
          those with it (core/views/collections.py — every thing whose only
          collection is this one), along with their questions and history. The
          owner is the only person who can do this and the only one warned, so
          the warning has to name what leaves that isn't theirs. */}
      <p>
        <strong>{t('deleteCollection.warning')}</strong>
      </p>
      <div className="spacer-s" />
      <p>{t('deleteCollection.whatGoesTitle')}</p>
      <ul className="measure">
        <li>{t('deleteCollection.goesThings')}</li>
        <li>{t('deleteCollection.goesFaq')}</li>
        <li>{t('deleteCollection.goesGuests')}</li>
      </ul>
      <div className="spacer-s" />
      <p className="measure">{t('deleteCollection.staysShared')}</p>
      <div className="spacer-s" />
      <p className="measure">
        <strong>{t('deleteCollection.backupNote')}</strong>
      </p>
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

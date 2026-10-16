import { useEffect, useState } from 'react';
import { useParams, useNavigate, useLocation } from 'react-router';
import { useTranslation, Trans } from 'react-i18next';
import { Button, IconCrossCircle } from 'hds-react';
import { apiFetch } from '../services/api';
import PageLayout from '../components/PageLayout';
import Toast from '../components/Toast';
import ThingsGoNotice from '../components/ThingsGoNotice';
import useTheeeme from '../hooks/useTheeeme';
import { useCollectionBase } from '../hooks/useCollectionBase';
import useDocumentTitle from '../hooks/useDocumentTitle';

export default function RemoveGuestPage() {
  const { t } = useTranslation();
  const { code } = useParams();
  const base = useCollectionBase(code);
  const navigate = useNavigate();
  const location = useLocation();
  const backPath = `${base}/invites`;
  const backLabel = location.state?.backLabel || t('removeGuest.guests');
  const guestCode = location.state?.guestCode;
  // Headlines of the member's things in this group, which are deleted with them.
  const thingTitles = location.state?.thingTitles;
  // The same stand-in the rest of the app uses for a member with no name set
  // (`ThingLinkbox`, `InboxNotifications`, HomePage): the copy interpolates it
  // mid-sentence, so the sentence still needs a subject.
  const guestName = location.state?.guestName || t('common.aMember');

  useEffect(() => {
    if (!guestCode) navigate(backPath);
  }, [guestCode, navigate, backPath]);

  useDocumentTitle(t('titles.removeGuest'));

  const [removing, setRemoving] = useState(false);
  const [toast, setToast] = useState(null);

  const handleRemove = async () => {
    setRemoving(true);
    setToast(null);
    try {
      const res = await apiFetch(`/api/v1/collections/${code}/invite/`, {
        method: 'DELETE',
        body: JSON.stringify({ user_code: guestCode }),
      });
      if (res.ok) {
        navigate(backPath);
      } else {
        setToast({ type: 'error', message: t('removeGuest.errorRemoving') });
      }
    } catch {
      setToast({ type: 'error', message: t('common.connectionError') });
    } finally {
      setRemoving(false);
    }
  };

  const { btnStyle, btnSecondaryStyle } = useTheeeme();

  return (
    <PageLayout
      title={t('removeGuest.pageTitle', { name: guestName })}
      backTo={backPath}
      backLabel={backLabel}
    >
      <p>
        <Trans
          i18nKey="removeGuest.warning"
          values={{ name: guestName }}
          components={[<strong key="0" />]}
        />
      </p>
      <ThingsGoNotice
        titles={thingTitles}
        label={t('removeGuest.thingsLabel')}
        body={(count, list) => t('removeGuest.thingsBody', { count, list })}
      />
      <div className="spacer-xs" />
      <div className="form-grid">
        <Button
          fullWidth
          disabled={removing}
          onClick={handleRemove}
          style={btnStyle}
          iconStart={<IconCrossCircle aria-hidden="true" />}
        >
          {removing ? t('common.removing') : t('common.remove')}
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

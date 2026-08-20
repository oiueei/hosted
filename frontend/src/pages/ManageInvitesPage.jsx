import { useCallback, useEffect, useRef, useState } from 'react';
import { useParams, useNavigate } from 'react-router';
import { useTranslation } from 'react-i18next';
import { TextInput, Button, Notification, Table, IconEnvelope, IconCrossCircle } from 'hds-react';
import { apiFetch, extractApiError } from '../services/api';
import PageLayout from '../components/PageLayout';
import LoadingSpinner from '../components/LoadingSpinner';
import Toast from '../components/Toast';
import TooltipButton from '../components/TooltipButton';
import BulkInviteCsv from '../components/BulkInviteCsv';
import useTheeeme from '../hooks/useTheeeme';
import { useLocalized } from '../utils/localized';

export default function ManageInvitesPage() {
  const { code } = useParams();
  const navigate = useNavigate();
  const { t } = useTranslation();
  // Owner content (headlines, tags) may carry one text per language.
  const L = useLocalized();
  const { tc, btnStyle } = useTheeeme();
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [invites, setInvites] = useState([]);
  const [pendingInvites, setPendingInvites] = useState([]);
  // Members' recommendations awaiting the owner's answer. Owner-only from the
  // serializer: they name someone who has not been contacted and does not know
  // they were suggested, and they carry the proposer's private note.
  const [proposals, setProposals] = useState([]);
  const [answering, setAnswering] = useState(null);
  const [collectionHeadline, setCollectionHeadline] = useState('');
  const headline = L(collectionHeadline);
  useEffect(() => { document.title = headline ? t('titles.guests', { headline }) : t('titles.guestsDefault'); }, [headline, t]);
  const [isOwner, setIsOwner] = useState(false);
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteLoading, setInviteLoading] = useState(false);
  const [toast, setToast] = useState(null);
  const [resending, setResending] = useState(null);
  const inviteLockRef = useRef(false);
  const resendLockRef = useRef(false);

  const fetchCollection = useCallback(async () => {
    try {
      const res = await apiFetch(`/api/v1/collections/${code}/`);
      if (res.ok) {
        const data = await res.json();
        setInvites(data.invites || []);
        setPendingInvites(data.pending_invites || []);
        setProposals(data.pending_proposals || []);
        setCollectionHeadline(data.headline || '');
        setIsOwner(localStorage.getItem('userCode') === data.owner);
        setLoadError('');
      } else {
        // A persistent error, not the auto-closing toast this used to raise.
        // The toast faded and left the page rendering isOwner=false over an
        // empty list — "no guests, and you can't invite anyone" — which is not
        // what happened. Every other data page in the app stops and says so.
        setLoadError(
          res.status === 403
            ? t('manageInvites.noPermission')
            : t('manageInvites.errorLoading'),
        );
      }
    } catch {
      setLoadError(t('common.connectionError'));
    } finally {
      setLoading(false);
    }
  }, [code, t]);

  useEffect(() => {
    // `react-hooks/set-state-in-effect` reads this as a setState in the effect
    // body, and here it is wrong: `fetchCollection` is async and its first
    // statement is the `await`, so every setState it makes happens in a
    // continuation the network schedules long after this render has painted —
    // there is no cascade to avoid. The rule cannot see past the `useCallback`,
    // and the shapes that would satisfy it (an inline copy of the fetch, or
    // bouncing the call through a resolved promise) each cost more than they
    // buy: this same function is what the approve/resend handlers re-run.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchCollection();
  }, [fetchCollection]);

  const answerProposal = async (proposalCode, decision) => {
    setAnswering(proposalCode);
    try {
      const res = await apiFetch(`/api/v1/proposals/${proposalCode}/${decision}/`, {
        method: 'POST',
      });
      if (res.ok) {
        setProposals((prev) => prev.filter((p) => p.code !== proposalCode));
        setToast({
          type: 'success',
          message: decision === 'approve'
            ? t('recommend.ownerApproved')
            : t('recommend.ownerDeclined'),
        });
        // An approval creates a pending invitation — reload so the guest list
        // shows it rather than looking as though nothing happened.
        if (decision === 'approve') fetchCollection();
      } else {
        const detail = await extractApiError(res);
        setToast({ type: 'error', message: detail || t('common.error') });
      }
    } catch {
      setToast({ type: 'error', message: t('common.connectionError') });
    } finally {
      setAnswering(null);
    }
  };

  const handleResend = async (email) => {
    if (resendLockRef.current) return;
    resendLockRef.current = true;
    setResending(email);
    try {
      const res = await apiFetch(`/api/v1/collections/${code}/invite/`, {
        method: 'POST',
        body: JSON.stringify({ email }),
      });
      if (res.ok) {
        setToast({ type: 'success', message: t('manageInvites.invitationResent') });
      } else {
        setToast({ type: 'error', message: t('manageInvites.errorResending') });
      }
    } catch {
      setToast({ type: 'error', message: t('common.connectionError') });
    } finally {
      setResending(null);
      resendLockRef.current = false;
    }
  };

  const handleInvite = async () => {
    if (inviteLockRef.current) return;
    inviteLockRef.current = true;
    setInviteLoading(true);
    setToast(null);
    try {
      const res = await apiFetch(`/api/v1/collections/${code}/invite/`, {
        method: 'POST',
        body: JSON.stringify({ email: inviteEmail.trim() }),
      });
      if (res.ok) {
        setPendingInvites((prev) => [...prev, { email: inviteEmail.trim() }]);
        setInviteEmail('');
        setToast({ type: 'success', message: t('manageInvites.invitationSent') });
      } else if (res.status === 429) {
        setToast({ type: 'error', message: t('common.tooManyAttempts') });
      } else {
        const detail = await extractApiError(res);
        setToast({ type: 'error', message: detail || t('manageInvites.errorSending') });
      }
    } catch {
      setToast({ type: 'error', message: t('common.connectionError') });
    } finally {
      setInviteLoading(false);
      inviteLockRef.current = false;
    }
  };

  if (loading) {
    return <LoadingSpinner />;
  }

  if (loadError) {
    return (
      <PageLayout
        title={t('common.error')}
        backTo={`/collections/${code}`}
        backLabel={t('common.collection')}
      >
        <Notification label={t('common.error')} type="error">{loadError}</Notification>
        <div className="spacer-m" />
        <Button variant="secondary" onClick={() => { setLoading(true); fetchCollection(); }}>
          {t('common.retry')}
        </Button>
      </PageLayout>
    );
  }

  return (
    <PageLayout
      title={t('manageInvites.pageTitle')}
      backTo={`/collections/${code}`}
      backLabel={headline || t('common.collection')}
    >
      {/* Members' recommendations, above the guest list because they are the
          thing waiting on the owner. Each shows who suggested whom and their
          note — an owner asked to admit an address they don't recognise needs
          the proposer's word to decide. Nothing has been sent to the person
          named here. */}
      {isOwner && proposals.length > 0 && (
        <>
          <h2>{t('recommend.ownerHeading')}</h2>
          <div className="spacer-s" />
          <p className="text-muted">{t('recommend.ownerIntro')}</p>
          <div className="spacer-s" />
          {proposals.map((p) => (
            <div key={p.code} className="proposal-card">
              <p className="proposal-who">
                <strong>{p.email}</strong>
                <span className="proposal-by">
                  {' '}{t('recommend.ownerBy', { name: p.proposer_name })}
                </span>
              </p>
              {p.note && <p className="proposal-note">“{p.note}”</p>}
              <div className="button-row-wide">
                <Button
                  style={btnStyle}
                  disabled={answering === p.code}
                  onClick={() => answerProposal(p.code, 'approve')}
                >
                  {t('recommend.ownerApprove')}
                </Button>
                <Button
                  variant="secondary"
                  disabled={answering === p.code}
                  onClick={() => answerProposal(p.code, 'reject')}
                >
                  {t('recommend.ownerReject')}
                </Button>
              </div>
            </div>
          ))}
          <div className="spacer-xl" />
        </>
      )}

      {invites.length === 0 && pendingInvites.length === 0 ? (
        <p>{t('manageInvites.noGuests')} {isOwner && t('manageInvites.noGuestsCta')}</p>
      ) : (() => {
        const tableRows = [
          ...invites.map((inv) => ({
            _id: inv.code,
            guest: inv.name ? `${inv.name} (${inv.email})` : inv.email,
            status: t('manageInvites.accepted'),
            _isPending: false,
            _email: inv.email,
            _code: inv.code,
            _name: inv.name || inv.email,
            _ageRange: inv.age_range || '',
            _postal: inv.postal_code || '',
          })),
          ...pendingInvites.map((p) => ({
            _id: p.code || `pending-${p.email}`,
            guest: p.email,
            status: t('manageInvites.pending'),
            _isPending: true,
            _email: p.email,
            _code: p.code,
            _name: p.email,
          })),
        ];
        const cols = [
          {
            key: 'guest',
            headerName: t('manageInvites.colGuest'),
            transform: (row) => (
              <div>
                <div>{row.guest}</div>
                {(row._ageRange || row._postal) && (
                  <div style={{ fontSize: 'var(--fontsize-body-s)', color: 'var(--color-black-60)' }}>
                    {[row._ageRange ? t(`ageRange.${row._ageRange}`) : null, row._postal]
                      .filter(Boolean)
                      .join(' · ')}
                  </div>
                )}
              </div>
            ),
          },
          { key: 'status', headerName: t('manageInvites.colStatus') },
          ...(isOwner ? [{
            key: '_actions',
            headerName: '',
            transform: (row) => (
              <div style={{ display: 'flex', gap: 'var(--spacing-xs)', alignItems: 'center', justifyContent: 'flex-end' }}>
                {row._isPending && (
                  <TooltipButton
                    tooltip={t('manageInvites.resendTooltip')}
                    onClick={() => handleResend(row._email)}
                    disabled={resending === row._email}
                  >
                    <IconEnvelope aria-hidden />
                  </TooltipButton>
                )}
                <TooltipButton
                  tooltip={t('manageInvites.removeTooltip')}
                  onClick={() => navigate(`/collections/${code}/invites/remove`, {
                    state: { guestCode: row._code, guestName: row._name, backLabel: headline || 'Guests' },
                  })}
                >
                  <IconCrossCircle aria-hidden />
                </TooltipButton>
              </div>
            ),
          }] : []),
        ];
        return (
          <Table
            cols={cols}
            rows={tableRows}
            indexKey="_id"
            renderIndexCol={false}
            theme={tc.color_03 ? { '--header-background-color': `var(--color-${tc.color_03})` } : undefined}
          />
        );
      })()}

      {isOwner && (
        <>
        <div className="spacer-xl" />
        <div className="form-grid section-mt">
          <TextInput
            id="manage-invites-email"
            label={t('manageInvites.emailLabel')}
            type="email"
            value={inviteEmail}
            onChange={(e) => setInviteEmail(e.target.value)}
            placeholder={t('manageInvites.emailPlaceholder')}
          />
          <Button
            disabled={inviteLoading || !inviteEmail.trim()}
            onClick={handleInvite}
            style={{ ...btnStyle, width: '100%' }}
          >
            {inviteLoading ? t('common.sending') : t('manageInvites.invite')}
          </Button>
        </div>
        <div className="spacer-m" />
        <h2>{t('bulkInvite.heading')}</h2>
        <BulkInviteCsv collectionCode={code} onInvited={fetchCollection} />
        </>
      )}

      <Toast toast={toast} onClose={() => setToast(null)} />
    </PageLayout>
  );
}

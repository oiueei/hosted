import { useEffect, useState } from 'react';
import { Link } from 'react-router';
import { useTranslation } from 'react-i18next';
import { Notification } from 'hds-react';
import { apiFetch } from '../services/api';
import { useLocalized } from '../utils/localized';

const ALERT_TYPES = new Set([
  'COLLECTION_DELETED',
  'COLLECTION_REVOKED',
  'BOOKING_REJECTED',
  'FAQ_HIDDEN',
  'INVITE_REJECTED',
  'THING_REPORTED',
  'INVITE_PROPOSAL_DECLINED',
]);
const SUCCESS_TYPES = new Set(['BOOKING_ACCEPTED', 'INVITE_PROPOSAL_APPROVED']);

// The owner said yes to a recommendation. Written as INVITE_PROPOSAL_APPROVED
// since the 2026-08 design round; rows created before that are an
// INVITE_PROPOSED carrying `approved: true`, and both must read the same.
const isProposalApproved = (n) =>
  n.type === 'INVITE_PROPOSAL_APPROVED' || (n.type === 'INVITE_PROPOSED' && n.payload?.approved);

const notificationType = (type) => {
  if (ALERT_TYPES.has(type)) return 'alert';
  if (SUCCESS_TYPES.has(type)) return 'success';
  return 'info';
};

/**
 * The inbox: one dismissible Notification per in-app notification.
 *
 * Rendered bare on Home (everything the user has) and scoped on a collection's own
 * page (`collection` — the owner sees a hold request where the thing actually lives,
 * not only on Home). Strings keep the `home.*` namespace they were born in.
 *
 * Props: `collection` (optional code to filter by), `reloadKey` (bump to re-fetch —
 * Home does it when connectivity returns), `onNetworkError` (a stable callback; Home
 * turns it into its offline banner).
 */
export default function InboxNotifications({ collection, reloadKey = 0, onNetworkError }) {
  const { t } = useTranslation();
  // Owner content in a payload (headlines) may carry one text per language.
  const L = useLocalized();
  const [notifications, setNotifications] = useState([]);

  useEffect(() => {
    const controller = new AbortController();
    const { signal } = controller;
    const fetchInbox = async () => {
      try {
        const url = collection
          ? `/api/v1/inbox/?collection=${encodeURIComponent(collection)}`
          : '/api/v1/inbox/';
        const res = await apiFetch(url, { signal });
        if (res.ok) {
          const data = await res.json();
          // Only ever render a list. This sits on top of Home and of every
          // collection page, so an unexpected body must degrade to "no
          // notifications", never take the whole page down with it.
          if (!signal.aborted && Array.isArray(data)) setNotifications(data);
        }
      } catch (err) {
        if (!signal.aborted) onNetworkError?.(err);
      }
    };
    fetchInbox();
    return () => controller.abort();
  }, [collection, reloadKey, onNetworkError]);

  const dismiss = async (code) => {
    setNotifications((prev) => prev.filter((n) => n.code !== code));
    try {
      await apiFetch(`/api/v1/inbox/${code}/`, { method: 'DELETE' });
    } catch (err) {
      onNetworkError?.(err);
    }
  };

  // Resolve the three headline keys once, then the builders below interpolate plain
  // words like they always did.
  //
  // The name keys get a stand-in for the same reason `ThingLinkbox` has always
  // used one: the backend sends the bare `name`, never `display_name`, because
  // the fallback in `display_name` is the person's email address and the reader
  // here is a co-member who is not entitled to it (L2). A person who never set a
  // name therefore arrives as `''`, and every one of these strings interpolates
  // the name mid-sentence — so without this the body reads " has replied to your
  // question about:". One funnel, so a builder cannot forget.
  const named = (value) => value || t('common.aMember');
  const localizedPayload = (payload) => ({
    ...payload,
    collection_headline: L(payload.collection_headline),
    thing_headline: L(payload.thing_headline),
    owner_name: named(payload.owner_name),
    questioner_name: named(payload.questioner_name),
    requester_name: named(payload.requester_name),
    invitee_name: named(payload.invitee_name),
    member_name: named(payload.member_name),
    proposer_name: named(payload.proposer_name),
  });

  const notificationLabel = (n) => {
    const p = localizedPayload(n.payload);
    switch (n.type) {
      case 'COLLECTION_DELETED':
        return t('home.collectionDeletedLabel');
      case 'COLLECTION_REVOKED':
        return t('home.collectionRevokedLabel');
      case 'BOOKING_ACCEPTED':
        return t('home.bookingAcceptedLabel');
      case 'BOOKING_REJECTED':
        return t('home.bookingRejectedLabel');
      case 'BOOKING_REQUESTED':
        return t('home.bookingRequestedLabel');
      case 'FAQ_QUESTION':
        return t('home.faqQuestionLabel');
      case 'FAQ_ANSWERED':
        return t('home.faqAnsweredLabel');
      case 'FAQ_HIDDEN':
        return t('home.faqHiddenLabel');
      case 'INVITE_REJECTED':
        return t('home.inviteRejectedLabel');
      case 'THING_REPORTED':
        return t('home.reportedLabel');
      case 'MEMBER_LEFT':
        return t('home.memberLeftLabel');
      case 'INVITE_PROPOSAL_APPROVED':
        return t('home.proposalApprovedLabel');
      case 'INVITE_PROPOSAL_DECLINED':
        return t('home.proposalDeclinedLabel');
      case 'INVITE_PROPOSED':
        return isProposalApproved(n) ? t('home.proposalApprovedLabel') : t('home.proposedLabel');
      default:
        return t('home.broadcastLabel', {
          owner_name: p.owner_name,
          collection_headline: p.collection_headline,
        });
    }
  };

  const notificationBody = (n) => {
    const p = localizedPayload(n.payload);
    switch (n.type) {
      case 'COLLECTION_DELETED':
        return t('home.collectionDeletedBody', {
          collection_headline: p.collection_headline,
          owner_name: p.owner_name,
        });
      case 'COLLECTION_REVOKED':
        return t('home.collectionRevokedBody', {
          collection_headline: p.collection_headline,
          owner_name: p.owner_name,
        });
      case 'BOOKING_ACCEPTED':
        return t('home.bookingAcceptedBody', {
          thing_headline: p.thing_headline,
          owner_name: p.owner_name,
        });
      case 'BOOKING_REJECTED':
        return t('home.bookingRejectedBody', {
          thing_headline: p.thing_headline,
          owner_name: p.owner_name,
        });
      case 'BOOKING_REQUESTED':
        return t('home.bookingRequestedBody', {
          thing_headline: p.thing_headline,
          requester_name: p.requester_name,
        });
      case 'FAQ_QUESTION':
        return t('home.faqQuestionBody', {
          thing_headline: p.thing_headline,
          questioner_name: p.questioner_name,
        });
      case 'FAQ_ANSWERED':
        return t('home.faqAnsweredBody', {
          thing_headline: p.thing_headline,
          owner_name: p.owner_name,
        });
      case 'FAQ_HIDDEN':
        return t('home.faqHiddenBody', {
          thing_headline: p.thing_headline,
          owner_name: p.owner_name,
        });
      case 'INVITE_REJECTED':
        return t('home.inviteRejectedBody', {
          collection_headline: p.collection_headline,
          invitee_name: p.invitee_name,
        });
      case 'THING_REPORTED':
        return t('home.reportedBody', { thing_headline: p.thing_headline });
      case 'MEMBER_LEFT':
        return t('home.memberLeftBody', {
          collection_headline: p.collection_headline,
          member_name: p.member_name,
        });
      case 'INVITE_PROPOSAL_APPROVED':
        return t('home.proposalApprovedBody', {
          collection_headline: p.collection_headline,
          email: p.email,
        });
      case 'INVITE_PROPOSAL_DECLINED':
        return t('home.proposalDeclinedBody', {
          collection_headline: p.collection_headline,
          email: p.email,
        });
      case 'INVITE_PROPOSED':
        return isProposalApproved(n)
          ? t('home.proposalApprovedBody', {
              collection_headline: p.collection_headline,
              email: p.email,
            })
          : t('home.proposedBody', {
              collection_headline: p.collection_headline,
              proposer_name: p.proposer_name,
              email: p.email,
            });
      default:
        return t('home.broadcastBody', { message: p.message });
    }
  };

  // Deep link to the object that originated a notification: the collection for a
  // broadcast, otherwise the thing it is about — a hold request is answered on the
  // thing, so the owner should land there in one click. Returns {to, label} or null.
  const notificationLink = (n) => {
    const p = n.payload || {};
    if (n.type === 'BROADCAST' && p.collection_code) {
      return { to: `/collections/${p.collection_code}`, label: t('home.viewCollection') };
    }
    // A pending recommendation is a question, and the guest list is where the
    // owner answers it — landing them on the collection would leave them hunting
    // for the button. The two resolved states just point at the group.
    if (n.type === 'INVITE_PROPOSED' && !isProposalApproved(n) && p.collection_code) {
      return { to: `/collections/${p.collection_code}/invites`, label: t('home.viewProposal') };
    }
    if (
      (n.type === 'MEMBER_LEFT' ||
        n.type === 'INVITE_PROPOSAL_APPROVED' ||
        n.type === 'INVITE_PROPOSAL_DECLINED' ||
        n.type === 'INVITE_PROPOSED') &&
      p.collection_code
    ) {
      return { to: `/collections/${p.collection_code}`, label: t('home.viewGroup') };
    }
    if (p.thing_code) {
      const to = p.collection_code
        ? `/collections/${p.collection_code}/things/${p.thing_code}`
        : `/things/${p.thing_code}`;
      return { to, label: t('home.viewThing') };
    }
    return null;
  };

  if (notifications.length === 0) return null;

  return (
    <>
      {notifications.map((n) => {
        const link = notificationLink(n);
        return (
          <Notification
            key={n.code}
            type={notificationType(n.type)}
            label={notificationLabel(n)}
            dismissible
            closeButtonLabelText={t('home.dismiss')}
            onClose={() => dismiss(n.code)}
            style={{ marginBottom: 'var(--spacing-s)' }}
          >
            {notificationBody(n)}
            {link && (
              <>
                {' '}
                <Link to={link.to}>{link.label}</Link>
              </>
            )}
          </Notification>
        );
      })}
      <div className="spacer-m" />
    </>
  );
}

import { useEffect, useState } from 'react';
import { useParams } from 'react-router';
import { useTranslation } from 'react-i18next';
import { apiFetch } from '../services/api';
import PageLayout from '../components/PageLayout';
import BulkInviteCsv from '../components/BulkInviteCsv';
import useCollectionLanguage from '../hooks/useCollectionLanguage';

/**
 * Invite several people at once, from a CSV. The tool was the
 * last block of `/collections/:code/invites`, under the form that invites one
 * address at a time; it moved to the collection menu, as
 * the CSV of things did (`ImportThingsPage`), and a menu entry only links,
 * so the tool needs a page of its own. Protected like `/invites` (`RequireAuth`),
 * reached from a curator's menu — "Invite many at once (CSV)", right after "Manage
 * members" — and the way back goes to "Manage members".
 *
 * **`onInvited` is not passed.** It only ever refreshed the list on `/invites`, a
 * page that is not on screen here and that reads the collection afresh when the
 * reader goes back to it; `BulkInviteCsv` shows its own result (how many were
 * invited, and which were skipped and why) in place, and the way back in the hero
 * is the clear route to the list.
 *
 * **No gate of its own**, on purpose, as on `ImportThingsPage`: the server decides who
 * may invite (`require_collection_curator`), and a barrier here that the server does
 * not have would only be a second rule to keep right. Someone who opens the address by
 * hand gets the tool, and the server's refusal when they send. The collection is read
 * for its language and nothing else.
 */
export default function ImportInvitesPage() {
  const { t } = useTranslation();
  const { code } = useParams();
  const userCode = localStorage.getItem('userCode');

  const [collectionLanguage, setCollectionLanguage] = useState('');
  useCollectionLanguage(collectionLanguage, []);

  useEffect(() => {
    document.title = t('titles.importInvites');
  }, [t]);

  useEffect(() => {
    if (!userCode) return;
    apiFetch(`/api/v1/collections/${code}/`)
      .then((res) => (res.ok ? res.json() : {}))
      .then((data) => setCollectionLanguage(data.language || ''))
      .catch(() => {});
  }, [userCode, code]);

  return (
    <PageLayout
      backTo={`/collections/${code}/invites`}
      backLabel={t('collectionPage.manageGuests')}
    >
      <h1 className="page-title-xl">{t('bulkInvite.heading')}</h1>
      <section className="bulk-add-section">
        <BulkInviteCsv collectionCode={code} />
      </section>
    </PageLayout>
  );
}

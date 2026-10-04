import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router';
import { useTranslation } from 'react-i18next';
import { apiFetch } from '../services/api';
import PageLayout from '../components/PageLayout';
import BulkAddCsv from '../components/BulkAddCsv';
import useCollectionLanguage from '../hooks/useCollectionLanguage';
import { useLocalized } from '../utils/localized';

/**
 * Add several things at once, from a CSV or a ZIP (X5, CA 2026-10-04). The tool
 * used to be a section at the foot of `/collections/:code/add` (`#bulk-add`), and
 * CA took it off that page ("it is already in the menu"): the collection menu's
 * "Add several at once (CSV)" entry only links, so the tool needs a page of its
 * own. Protected like `/add` (`RequireAuth`), reached from a curator's menu only —
 * a member of a COMMUNITY group keeps adding one at a time.
 *
 * **No gate of its own**, on purpose: someone who opens the address by hand is
 * treated exactly as `/add` treats them, because the server decides who may add
 * things (`ThingBulkCreateView`: `can_add_thing`) and a barrier here that the server
 * does not have would only be a second rule to keep right. The collection is read
 * for its name (the way back) and its language, and nothing else; a collection that
 * cannot be read leaves the generic back label and the tool as it is. After an
 * import it returns to the collection, as it did from `/add`.
 */
export default function ImportThingsPage() {
  const { t } = useTranslation();
  // Owner content (the collection's headline) may carry one text per language.
  const L = useLocalized();
  const { code } = useParams();
  const navigate = useNavigate();
  const userCode = localStorage.getItem('userCode');

  const [collectionHeadline, setCollectionHeadline] = useState('');
  const [collectionLanguage, setCollectionLanguage] = useState('');
  useCollectionLanguage(collectionLanguage, [collectionHeadline]);

  useEffect(() => {
    document.title = t('titles.importThings');
  }, [t]);

  useEffect(() => {
    if (!userCode) return;
    apiFetch(`/api/v1/collections/${code}/`)
      .then((res) => (res.ok ? res.json() : {}))
      .then((data) => {
        setCollectionHeadline(data.headline || '');
        setCollectionLanguage(data.language || '');
      })
      .catch(() => {});
  }, [userCode, code]);

  return (
    <PageLayout
      backTo={`/collections/${code}`}
      backLabel={L(collectionHeadline) || t('common.collection')}
    >
      <h1 className="page-title-xl">{t('collectionPage.addManyCsv')}</h1>
      <section className="bulk-add-section">
        <BulkAddCsv collectionCode={code} onImported={() => navigate(`/collections/${code}`)} />
      </section>
    </PageLayout>
  );
}

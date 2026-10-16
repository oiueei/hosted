import { useTranslation } from 'react-i18next';
import { useLocation } from 'react-router';
import PageLayout from '../components/PageLayout';
import ButtonLink from '../components/ButtonLink';
import ApprovalNotice from '../components/ApprovalNotice';
import useCapabilities, { isOfferable } from '../hooks/useCapabilities';
import useTheeeme from '../hooks/useTheeeme';
import { COLLECTION_KINDS, kindSegment } from '../utils/collectionPath';
import useDocumentTitle from '../hooks/useDocumentTitle';

/**
 * `/new` — what kind of collection is this? Three cards, one destination each:
 * a stall (to sell or give away), a library (to lend or rent out) or a shed (to
 * book by the day or by the hour). The kind is fixed for good when the
 * collection is created, so it is chosen here, before the form, and the form
 * lives at `/{kind}/new`; the hero says so (`kinds.chooseIntro`), and each card says
 * what separates its kind from the others (a library's things go home with whoever
 * takes them, a shed is used where it stands).
 *
 * A deployment that does not hand a kind out to this account (`collection_kinds`
 * on `GET /auth/me/`, derived from the verbs its policy offers) still shows the
 * card — nothing disappears without a word — but without its button, and with
 * the same "needs approval" line the forms use. Whoever opens the page may say
 * how to come back (`state.backPath` / `state.backLabel`, as `CreateCollectionPage`
 * reads them); the arrow honours it and each button hands it on to the form. Unknown capabilities offer
 * everything: the server is the gate.
 */
export default function NewCollectionPage() {
  const { t } = useTranslation();
  const capabilities = useCapabilities();
  const { btnStyle } = useTheeeme();
  const location = useLocation();
  const backPath = location.state?.backPath || '/';
  const backLabel = location.state?.backLabel || t('common.home');

  useDocumentTitle(t('titles.newCollection'));

  return (
    <PageLayout
      title={t('createCollection.pageTitle')}
      description={t('kinds.chooseIntro')}
      backTo={backPath}
      backLabel={backLabel}
    >
      <ul className="kind-cards">
        {COLLECTION_KINDS.map((kind) => {
          const long = t(`kinds.${kind}.long`);
          const open = isOfferable(capabilities, 'collection_kinds', kind);
          return (
            <li key={kind} className="kind-card">
              <h2 className="kind-card-title">{long}</h2>
              <p className="kind-card-what">{t(`kinds.${kind}.what`)}</p>
              {open ? (
                <div className="button-row-wide">
                  <ButtonLink
                    to={`/${kindSegment(kind)}/new`}
                    state={location.state}
                    style={btnStyle}
                  >
                    {t(`kinds.${kind}.create`)}
                  </ButtonLink>
                </div>
              ) : (
                <ApprovalNotice
                  kind="collection_kinds"
                  catalogue={[{ value: kind, label: long }]}
                />
              )}
            </li>
          );
        })}
      </ul>
    </PageLayout>
  );
}

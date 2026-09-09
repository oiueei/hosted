import { Link } from 'react-router';
import { useTranslation } from 'react-i18next';
import MagicLinkJoinPage from '../../components/MagicLinkJoinPage';
import { faqPath } from '../index';

// This deployment's open door has no target — no share token, no collection
// code — which is exactly the case `/auth/join/` refuses to create anything
// for (upstream, an account exists because somebody chose to admit that
// person). The account this page creates instead lands through the `hosted`
// app's own endpoint (`PopInView`, `hosted/views.py`), mounted at the
// historical `/api/v1/auth/pop-in/` path. Posting this form to `/auth/join/`
// — the shared `useJoin`/`MagicLinkJoinPage` default — silently created and
// sent nothing: the unified response looked identical either way.
const POP_IN_ENDPOINT = '/api/v1/auth/pop-in/';

export default function PopInPage() {
  const { t } = useTranslation();
  return (
    <MagicLinkJoinPage
      ns="popin"
      docTitleKey="titles.popin"
      titleKey="popin.title"
      descriptionKey="popin.description"
      endpoint={POP_IN_ENDPOINT}
    >
      {/* The fourth of the four FAQ links the August round asked for — the door
          with the most first-time traffic. `MagicLinkJoinPage`'s `children`
          slot renders it under the form. */}
      {faqPath && (
        <p>
          <Link to={faqPath}>{t('popin.faqLink')}</Link>
        </p>
      )}
    </MagicLinkJoinPage>
  );
}

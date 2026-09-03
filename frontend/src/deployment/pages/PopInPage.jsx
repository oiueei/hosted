import MagicLinkJoinPage from '../../components/MagicLinkJoinPage';

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
  return (
    <MagicLinkJoinPage
      ns="popin"
      docTitleKey="titles.popin"
      titleKey="popin.title"
      descriptionKey="popin.description"
      endpoint={POP_IN_ENDPOINT}
    />
  );
}

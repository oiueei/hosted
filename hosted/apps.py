from django.apps import AppConfig


class HostedConfig(AppConfig):
    """The service layer of a hosted OIUEEI — this deployment's, not the product's.

    Everything in this app is one operator's business decision: the open sign-up
    door, the page that explains what *this* service is, who is allowed to run a
    community collection or lend things, and (one day) what any of it costs.
    None of it belongs upstream, where a self-hoster would have to delete it
    before their own answers could apply.

    It only ever **adds**. It mounts its URLs through `DEPLOYMENT_URLCONFS`,
    supplies a `CREATOR_POLICY`, and replaces `frontend/src/deployment/` — the
    four extension points documented in SELF_HOSTING.md. It imports from
    `core`; `core` knows nothing about it, which is what keeps a merge from
    upstream a merge rather than an argument.

    Its models live in its own `migrations/`, so `core/migrations/` — a log
    shared by two databases of the same lineage — never forks.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "hosted"

"""A deploy-time check for `CREATOR_POLICY`, the setting a deployment points at
its own code.

`CREATOR_POLICY` names a class by dotted path, and it is resolved **lazily** —
on the first call to `get_creator_policy()`, which is to say on the first
request that creates something or asks `GET /auth/me/`. Nothing reads it at
startup, so before this check `manage.py check` passed, the Heroku `release`
phase (which runs `migrate`) passed, the dyno booted, and a typo surfaced only
as a 500.

That 500 is the expensive part. `/auth/me/` is what the SPA calls on **every**
app load, so a one-character mistake in a config var does not degrade a corner
of the product — it takes the whole frontend down for everyone, after the deploy
has already been declared successful. This check turns that into a failed
deploy, where it costs nobody anything.

It deliberately does the same work the runtime does — import the path *and*
instantiate it — because a check that merely inspected the string would pass on
a path whose module raises at import time, or whose `__init__` needs arguments.

**`DEPLOYMENT_URLCONFS` deliberately has no twin here.** It is resolved when the
URLconf is built, and Django's own `check_url_config` is registered as the
checks framework is imported — before any app's `ready()` — so it always runs
first and already fails the deploy on an unimportable module or one with no
`urlpatterns`. A second check could never win that race; it would only rot.
"""

from django.conf import settings
from django.core.checks import Error, register
from django.utils.module_loading import import_string


@register()
def check_creator_policy(app_configs, **kwargs):
    """`CREATOR_POLICY` names a real, importable, instantiable `CreatorPolicy`."""
    from core.services.creator_policy import CreatorPolicy

    path = getattr(settings, "CREATOR_POLICY", "")
    if not path:
        return [
            Error(
                "CREATOR_POLICY is empty.",
                hint=(
                    "Unset it to take the default "
                    "(core.services.creator_policy.OpenCreatorPolicy), which is "
                    "OIUEEI as a product: anyone with an account may create anything."
                ),
                id="core.E001",
            )
        ]

    try:
        policy_class = import_string(path)
    except ImportError as exc:
        return [
            Error(
                f"CREATOR_POLICY points at {path!r}, which cannot be imported: {exc}",
                hint=(
                    "Every collection and thing created on this deployment asks this "
                    "class, and GET /auth/me/ serves what it answers — so an "
                    "unimportable path 500s the endpoint the SPA calls on every load."
                ),
                id="core.E002",
            )
        ]

    if not (isinstance(policy_class, type) and issubclass(policy_class, CreatorPolicy)):
        return [
            Error(
                f"CREATOR_POLICY points at {path!r}, which is not a CreatorPolicy subclass.",
                hint=(
                    "Subclass core.services.creator_policy.CreatorPolicy and "
                    "override capabilities()."
                ),
                id="core.E003",
            )
        ]

    try:
        # Instantiated the way `get_creator_policy()` does. A subclass whose
        # __init__ needs arguments would import cleanly and then fail on the
        # first request, which is the failure mode this whole module exists for.
        policy_class()
    except Exception as exc:  # noqa: BLE001 — any failure here is a broken deployment
        return [
            Error(
                f"CREATOR_POLICY {path!r} could not be instantiated: {exc!r}",
                hint=(
                    "It is constructed once with no arguments and shared across "
                    "requests, so it must take none and must be stateless."
                ),
                id="core.E004",
            )
        ]

    return []

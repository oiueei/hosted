"""Deploy-time checks for the settings that only fail once somebody uses them.

Both checks here guard the same class of outage rather than a feature: a setting
that nothing reads at startup passes `manage.py check`, passes the Heroku
`release` phase, boots a healthy dyno — and then surfaces as a 500 on a request,
after the deploy has already been declared successful.

## `CREATOR_POLICY`, the setting a deployment points at its own code

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

## `OBJECT_STORAGE_*`, the five that have to be set together

Storage is **optional**: unset, the app runs and serves everything it already
has, which is what keeps a checkout usable without an account. That is a
supported state and the check below leaves it alone.

What it catches is the state in between. Set four of the five and the deployment
looks entirely healthy — `MEDIA_PUBLIC_BASE_URL` still derives from the endpoint
and bucket, so existing images render and the CSP is right — while
`storage._config()` raises `ImproperlyConfigured` on the first upload anybody
attempts. Nothing before that moment says a word. All-or-none is the real
contract, so it is worth stating at deploy time rather than discovering from a
user who could not add a photo.
"""

from django.conf import settings
from django.core.checks import Error, Warning, register
from django.utils.module_loading import import_string

# The five that make up one credential set (`core/services/storage.py::_config`).
_STORAGE_SETTINGS = (
    "OBJECT_STORAGE_ENDPOINT",
    "OBJECT_STORAGE_BUCKET",
    "OBJECT_STORAGE_REGION",
    "OBJECT_STORAGE_ACCESS_KEY",
    "OBJECT_STORAGE_SECRET_KEY",
)


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


@register()
def check_object_storage(app_configs, **kwargs):
    """The five `OBJECT_STORAGE_*` settings are either all set, or all unset.

    A `Warning`, not an `Error`: unlike `CREATOR_POLICY` — which every deployment
    has, and whose default is a real value — storage is genuinely optional, and
    an `Error` would refuse to start the very checkout this setting is optional
    for. A half-configured one is still always a mistake, so it must be said out
    loud; `manage.py check --fail-level WARNING` is there for a deployment that
    wants it fatal.
    """
    missing = [name for name in _STORAGE_SETTINGS if not getattr(settings, name, "")]
    if not missing or len(missing) == len(_STORAGE_SETTINGS):
        return []
    return [
        Warning(
            "Object storage is half-configured: " + ", ".join(missing) + " unset.",
            hint=(
                "The five OBJECT_STORAGE_* settings are one credential set. With some "
                "of them the app boots, serves every image it already has and reports "
                "nothing wrong — and then answers 500 on the first upload anybody "
                "tries. Set all five, or none (uploads are simply off)."
            ),
            id="core.W001",
        )
    ]

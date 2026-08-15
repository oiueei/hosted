"""Who may create what, on this deployment.

OIUEEI as a product says: anyone with an account creates any collection and
offers a thing under any of the four verbs. That is what `OpenCreatorPolicy`
below encodes, and it is what an upstream checkout does — **the standalone has
no gate, and adding this module does not add one.**

A particular deployment may want a narrower answer. A cooperative might let
only its board open COMMUNITY collections; an operator running OIUEEI as a
service might vet whoever asks to lend or rent before the verb is available to
them. Both of those are *deployment* rules rather than product rules, so
neither belongs in this repository — but the **place to hang them** does, or
every such deployment ends up patching `CollectionCreateSerializer` and
re-patching it after each upgrade.

`CREATOR_POLICY` names the class, the way `AUTH_USER_MODEL` names a model. Swap
it and the whole product obeys, because there is exactly one source of truth:

- The *enforcement* points ask `collection_mode_denial()` / `thing_type_denial()`
  and turn a message into a 403.
- The *UI* reads the same policy through `capabilities` on `GET /auth/me/` and
  never offers what would be refused.

Both are computed from the same `capabilities()` call, so the frontend cannot
drift into offering something the backend will reject — the failure mode of
every gate that is written twice.

What a policy is **not**: it is not permission to touch a specific object (that
is `IsCollectionOwner` and friends), and it is not the owner's own per-collection
`allowed_thing_types` allowlist (`core.views._helpers.type_validity_error`). This
answers only "may this person bring such a thing into existence here at all".
"""

from dataclasses import dataclass
from functools import lru_cache

from django.conf import settings
from django.utils.module_loading import import_string

from core.models import Collection, Thing


@dataclass(frozen=True)
class Capabilities:
    """What one user may create here — the whole of what a policy decides.

    `request_url` is where someone goes to ask for what they were not given.
    `None` means there is nowhere to ask, which is the standalone's answer
    because there is nothing to ask for. The frontend only shows the "this
    needs approval" notice when a capability is missing *and* this is set;
    that pairing is deliberate, since a deployment that quietly narrows the
    product without saying where to appeal leaves the user staring at a
    disabled control with no explanation.
    """

    collection_modes: tuple[str, ...]
    thing_types: tuple[str, ...]
    request_url: str | None = None

    def as_dict(self):
        """The JSON shape served by `GET /auth/me/` (lists, not tuples)."""
        return {
            "collection_modes": list(self.collection_modes),
            "thing_types": list(self.thing_types),
            "request_url": self.request_url,
        }


class CreatorPolicy:
    """Base class: answer `capabilities()`, and the rest follows.

    Subclasses override that one method. The two `allows_*` helpers are derived
    from it on purpose — a policy that could answer "yes" to a mode it left out
    of its own capabilities would be a policy the UI misreports.

    Instances are cached per dotted path (see `get_creator_policy`) and shared
    across requests, so a subclass must be **stateless**: everything it needs
    arrives in `user`.
    """

    def capabilities(self, user) -> Capabilities:
        raise NotImplementedError

    def allows_collection_mode(self, user, mode) -> bool:
        return mode in self.capabilities(user).collection_modes

    def allows_thing_type(self, user, thing_type) -> bool:
        return thing_type in self.capabilities(user).thing_types


class OpenCreatorPolicy(CreatorPolicy):
    """Yes, to everyone, always. The standalone default.

    The lists come from the models' own choices rather than being spelled out
    here, so a verb added to `Thing.Type` is available the day it is added
    instead of the day someone remembers this file.
    """

    def capabilities(self, user) -> Capabilities:
        return Capabilities(
            collection_modes=tuple(Collection.Mode.values),
            thing_types=tuple(Thing.Type.values),
            request_url=None,
        )


@lru_cache(maxsize=None)
def _policy_instance(dotted_path):
    return import_string(dotted_path)()


def get_creator_policy() -> CreatorPolicy:
    """The policy this deployment runs, instantiated once per dotted path.

    The setting is read on every call and the *instance* is what gets cached,
    so `override_settings(CREATOR_POLICY=...)` works in tests while a live
    deployment never re-imports.
    """
    return _policy_instance(settings.CREATOR_POLICY)


def collection_mode_denial(user, mode) -> str | None:
    """Why this deployment won't let `user` create a `mode` collection, else `None`.

    A message rather than an exception: `core/services` stays free of HTTP, the
    way `booking_service` does, and each call site raises the 403 itself. The
    wording lives here so the four enforcement points can't drift apart.
    """
    policy = get_creator_policy()
    if policy.allows_collection_mode(user, mode):
        return None
    return _denial(
        f"This deployment does not allow you to create {mode} collections.",
        policy.capabilities(user).request_url,
    )


def thing_type_denial(user, thing_type) -> str | None:
    """Why this deployment won't let `user` offer a `thing_type`, else `None`."""
    policy = get_creator_policy()
    if policy.allows_thing_type(user, thing_type):
        return None
    label = thing_type.replace("_", " ").lower()
    return _denial(
        f"This deployment does not allow you to offer a {label}.",
        policy.capabilities(user).request_url,
    )


def _denial(message, request_url):
    """Append where to ask, when there is somewhere.

    The 403 body carries it as well as `GET /auth/me/` because the API is
    usable without the SPA, and a client that only ever sees the refusal would
    otherwise have no way to learn that asking is even possible.
    """
    return f"{message} Request access at {request_url}." if request_url else message

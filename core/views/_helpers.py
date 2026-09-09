"""Shared view helpers for OIUEEI."""

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response

from core.models import Thing


def body_dict(request):
    """``request.data`` when the body is a JSON object, else an empty dict.

    DRF parses a JSON *array* body into a ``list``, which has no ``.get`` — so a
    view that reads ``request.data.get(...)`` before any serializer has run
    raises ``AttributeError`` and answers 500 where it owes a 400. Every endpoint
    using this expects an object body, so anything else is simply "no fields
    given" and falls through to the view's own validation, which already has the
    right message for an empty request.
    """
    return request.data if isinstance(request.data, dict) else {}


def viewer_code(request):
    """The requesting user's code, or ``None`` for an anonymous visitor.

    The public-read endpoints accept anonymous callers, but ``request.user`` is
    then an ``AnonymousUser`` with no ``.code``. Centralise the guard so each
    view passes a real code — or ``None`` — straight into the ``can_view``
    helpers (which treat ``None`` as "anonymous": PUBLIC collections only).
    """
    user = request.user
    return user.code if user.is_authenticated else None


def deny_if_cannot_view(obj, user_code, message):
    """Return a 403 ``{"error": message}`` Response if ``user_code`` cannot view
    ``obj`` (a Thing), else ``None``.

    Centralises the ``can_view`` authorisation guard so every endpoint returns the
    same ``{"error": ...}`` shape (one endpoint previously used ``{"detail": ...}``).
    """
    if not obj.can_view(user_code):
        return Response({"error": message}, status=status.HTTP_403_FORBIDDEN)
    return None


def get_viewable_thing(code, user_code, message):
    """``get_object_or_404(Thing, code=code)`` followed by the ``can_view`` guard.

    Returns ``(thing, None)`` on success, or ``(thing, Response)`` when the user
    cannot view it — callers do ``thing, denied = ...; if denied: return denied``.
    """
    thing = get_object_or_404(Thing, code=code)
    return thing, deny_if_cannot_view(thing, user_code, message)


def type_validity_error(thing_type, collection):
    """Error message if ``thing_type`` isn't valid for ``collection``, else None.

    Shared by thing create/update AND the collection add-thing endpoint so the
    owner's per-collection allowlist can't be bypassed by any path (L4). A thing
    with no collection has no allowlist to answer to, so it is always valid —
    the type-vs-mode rules that used to live here went with SHARE and SWAP.

    RESERVE_THING is the one type with a rule of its own: it can *only* live in
    a reservations collection (``allowed_thing_types == ["RESERVE_THING"]``), so
    a standalone RESERVE thing — or one aimed at any other collection — is
    refused. The ``["RESERVE_THING"]`` allowlist already blocks the other four
    types from a reservations collection; this closes the other direction.
    """
    if thing_type == "RESERVE_THING":
        if collection is None or not collection.is_reservations_collection():
            return (
                "A reservation can only be added to a reservations collection "
                "(one that offers reservations and nothing else)."
            )
        return None
    if collection is None:
        return None
    if collection.allowed_thing_types and thing_type not in collection.allowed_thing_types:
        return (
            f"This collection does not accept {thing_type.replace('_', ' ').title()}s."
            " The owner has restricted it to specific types."
        )
    return None


def require_collection_curator(collection, user_code, message):
    """Return a 403 ``{"error": message}`` Response if ``user_code`` is neither
    the collection owner nor a co-owner, else ``None``.

    Used by every collection APIView that a co-curator shares with the founder
    (invite, share-link, broadcast, stats, export, proposal decisions, and
    promoting/demoting a co-curator) instead of the ``IsCollectionCurator``
    DRF permission, so each keeps its own specific ``{"error": ...}`` message
    rather than DRF's generic ``{"detail": ...}`` body. Deleting the
    collection is the one action still owner-only, and it uses the
    ``IsCollectionOwner`` permission class directly.
    """
    if not collection.is_curator(user_code):
        return Response({"error": message}, status=status.HTTP_403_FORBIDDEN)
    return None

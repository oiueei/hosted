"""
The two data-download endpoints (GDPR art. 20 and the group copy).

Both are plain `HttpResponse` attachments rather than DRF `Response` bodies:
what these return is a **file**, and a file has a name, a disposition and a
caching rule that a rendered JSON body doesn't carry. The tree itself is built
by `core.services.export_service`, which is also where the reasoning about what
never leaves lives; this module is the HTTP layer around it — who may ask, how
often, and what the browser is allowed to do with the answer.
"""

import logging

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django_ratelimit.decorators import ratelimit
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from core.models import Collection
from core.services.export_service import (
    build_account_export,
    build_collection_export,
    export_bytes,
    export_filename,
)
from core.views._helpers import require_collection_owner

security_logger = logging.getLogger("security")

# A copy of everything you own is not something anyone needs often, and building
# one is the heaviest read in the app. Ten a day leaves room for "that download
# went wrong, try again" and none for walking a server out one export at a time.
EXPORT_RATE = "10/d"


def _download(payload, code):
    """The shared response shape: a JSON attachment nothing is allowed to keep.

    `private, no-store` because the alternative is a shared proxy — or a
    browser's back/forward cache on a borrowed laptop — holding somebody's
    entire account in a file that was never meant to outlive the click.
    """
    response = HttpResponse(export_bytes(payload), content_type="application/json")
    response["Content-Disposition"] = f'attachment; filename="{export_filename(code)}"'
    response["Cache-Control"] = "private, no-store"
    return response


class AccountDataExportView(APIView):
    """
    GET /api/v1/auth/export/

    Your own data, as one JSON file (`oiueei-{user_code}-{date}.json`). The
    self-service half of the right the privacy policy used to answer with
    "write to me", and the twin of `AccountDeleteRequestView` — the same account
    page offers both, in that order, because reading your copy before erasing it
    is the sane sequence and the legally solid one.

    Rate-limited per user; logged to `security` like every other account action,
    with the size, since a sudden change in what an export weighs is the first
    sign that it started carrying something new.
    """

    permission_classes = [IsAuthenticated]

    @method_decorator(ratelimit(key="user", rate=EXPORT_RATE, method="GET", block=True))
    def get(self, request):
        response = _download(build_account_export(request.user), request.user.code)
        security_logger.info(
            f"Account data exported for {request.user.code} ({len(response.content)} bytes)"
        )
        return response


class CollectionDataExportView(APIView):
    """
    GET /api/v1/collections/{collection_code}/export/

    A whole group as its owner runs it, other members' things included —
    **owner-only**, and a member gets 403 rather than a smaller file. There is no
    partial export by design: "some of the group, depending on who asks" is a
    second access-control model to keep correct forever, and the thing a member
    is entitled to is their own account copy.

    Deliberately not folded into the account export: a collection of 4,000
    things would bloat every personal download, this button belongs next to the
    stats CSV, and keeping them apart lets the account copy stay honestly framed
    as *your* data while this one is what it is — an operational copy of a group,
    carrying other people's details, which the page says out loud.
    """

    permission_classes = [IsAuthenticated]

    @method_decorator(ratelimit(key="user", rate=EXPORT_RATE, method="GET", block=True))
    def get(self, request, collection_code):
        collection = get_object_or_404(Collection, code=collection_code)
        denied = require_collection_owner(
            collection, request.user.code, "Only the owner can export this collection"
        )
        if denied:
            return denied

        response = _download(build_collection_export(collection), collection.code)
        security_logger.info(
            f"Collection {collection.code} exported by {request.user.code} "
            f"({len(response.content)} bytes)"
        )
        return response

"""
The data-download endpoints (GDPR art. 20, the group copy, and the calendar CSV).

All are plain `HttpResponse` attachments rather than DRF `Response` bodies:
what these return is a **file**, and a file has a name, a disposition and a
caching rule that a rendered JSON body doesn't carry. The trees themselves are
built by `core.services.export_service` and `core.services.calendar_export_service`,
which is also where the reasoning about what never leaves lives; this module is
the HTTP layer around them — who may ask, how often, and what the browser is
allowed to do with the answer.
"""

import logging

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django_ratelimit.decorators import ratelimit
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from core.models import Collection
from core.services.calendar_export_service import build_calendar_export, calendar_filename
from core.services.export_service import (
    build_account_export,
    build_collection_export,
    export_bytes,
    export_filename,
)
from core.views._helpers import require_collection_curator

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

    A whole group as its owner (or a co-owner) runs it, other members' things
    included — **curator-only**, and a plain member gets 403 rather than a
    smaller file. There is no partial export by design: "some of the group,
    depending on who asks" is a second access-control model to keep correct
    forever, and the thing a member is entitled to is their own account copy.

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
        denied = require_collection_curator(
            collection, request.user.code, "Only the owner or a co-owner can export this collection"
        )
        if denied:
            return denied

        response = _download(build_collection_export(collection), collection.code)
        security_logger.info(
            f"Collection {collection.code} exported by {request.user.code} "
            f"({len(response.content)} bytes)"
        )
        return response


# A download, and a curator may legitimately press it again after a failed save
# or to pick up a reservation confirmed since. Higher than the JSON exports
# (which are the heaviest read in the app); still a cap, because each call is a
# write.
CALENDAR_EXPORT_RATE = "20/h"


class CollectionCalendarExportView(APIView):
    """
    POST /api/v1/collections/{collection_code}/calendar-export/

    The collection's upcoming date-based reservations (loans, rentals, on-site
    reservations) as a Google Calendar CSV — one all-day event per reservation,
    spanning its block. **Incremental**: each call returns only what has not
    been exported for this collection before and records that it has, so
    importing the file twice never doubles the calendar. `X-Calendar-Events`
    carries the count (0 ⇒ header only, and the SPA offers no download).

    **POST, not GET**, for the same reason `DigestMuteByTokenView` is: the call
    mutates (it marks the reservations delivered), so a mail-client link
    scanner or a browser prefetch must not be able to fire it.

    Curator-only (owner or co-owner); the mark is per collection, since a
    PROPRIETARY collection's curators run its catalogue together — see
    [`calendar_export_service`](../services/CLAUDE.md).
    """

    permission_classes = [IsAuthenticated]

    @method_decorator(ratelimit(key="user", rate=CALENDAR_EXPORT_RATE, method="POST", block=True))
    def post(self, request, collection_code):
        collection = get_object_or_404(Collection, code=collection_code)
        denied = require_collection_curator(
            collection, request.user.code, "Only the owner or a co-owner can export the calendar"
        )
        if denied:
            return denied

        csv_bytes, count = build_calendar_export(collection, user=request.user)
        response = HttpResponse(csv_bytes, content_type="text/csv")
        response["Content-Disposition"] = (
            f'attachment; filename="{calendar_filename(collection.code)}"'
        )
        response["Cache-Control"] = "private, no-store"
        response["X-Calendar-Events"] = str(count)
        security_logger.info(
            f"Collection {collection.code} calendar exported by {request.user.code} "
            f"({count} events, {len(csv_bytes)} bytes)"
        )
        return response

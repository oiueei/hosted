"""
In-app notification inbox views.
"""

from django.shortcuts import get_object_or_404
from rest_framework.exceptions import MethodNotAllowed
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from ..models.notification import InAppNotification

# The one group `DELETE /inbox/?group=` knows: the request and reservation notices
# that are for the team that manages them.
BOOKINGS_GROUP = "bookings"


class InboxView(APIView):
    """
    GET  /api/v1/inbox/         — list unread notifications for current user
    GET  /api/v1/inbox/?collection={code} — only the ones about that collection
    DELETE /api/v1/inbox/{code}/ — dismiss (delete) a notification
    DELETE /api/v1/inbox/?group=bookings[&collection={code}] — dismiss, in one go,
        the caller's request and reservation notices that are for the team that
        manages them (`InAppNotification.team_booking_notices`), the same set the
        inbox folds into one summary card. Only the caller's own, only those types,
        and with ``collection`` only the ones born in it (the same filter as the GET)

    Both routes resolve to this one view, so each handler takes an optional
    ``code`` and rejects the combination it doesn't serve (list has no code to
    delete; the item route has no list to GET) with a clean 405 instead of the
    TypeError-driven 500 that a signature mismatch would otherwise raise.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, code=None):
        if code is not None:
            # There is no single-notification GET — only the collection is listable.
            raise MethodNotAllowed("GET")
        notifications = self._scoped(request, InAppNotification.objects.filter(user=request.user))
        return Response(
            [
                {"code": n.code, "type": n.type, "payload": n.payload, "created": n.created}
                for n in notifications
            ]
        )

    @staticmethod
    def _scoped(request, notifications):
        # A collection's own page shows the notifications born in it, so the owner
        # sees a hold request where the thing lives — not only on Home. Payloads
        # written before the key existed carry no collection and never match.
        collection = (request.query_params.get("collection") or "").strip()
        if collection:
            notifications = notifications.filter(payload__collection_code=collection)
        return notifications

    def delete(self, request, code=None):
        if code is None:
            group = request.query_params.get("group")
            if group is None:
                # Dismiss targets a specific notification, or one named group.
                raise MethodNotAllowed("DELETE")
            if group != BOOKINGS_GROUP:
                return Response({"error": "Unknown group"}, status=400)
            mine = InAppNotification.objects.filter(user=request.user)
            self._scoped(request, InAppNotification.team_booking_notices(mine)).delete()
            return Response(status=204)
        notification = get_object_or_404(InAppNotification, code=code, user=request.user)
        notification.delete()
        return Response(status=204)

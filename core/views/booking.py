"""
Booking views for OIUEEI lending calendar.

All email action links use RSVP codes as intermediaries.
Accept/reject can also be done by the owner via authenticated API endpoints.
"""

from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models.booking import BookingPeriod
from core.models.collection import Collection
from core.models.rsvp import RSVP
from core.models.thing import Thing
from core.pagination import StandardResultsPagination
from core.serializers.booking import (
    BookingPeriodCalendarSerializer,
    BookingPeriodOwnerCalendarSerializer,
    BookingPeriodSerializer,
    MyBookingSerializer,
)
from core.services.booking_service import (
    BookingRequestError,
    cancel_booking,
    cancel_reservation,
    finalize_booking_decision,
)
from core.views._helpers import get_viewable_thing, viewer_code


class ThingCalendarView(APIView):
    """
    GET /api/v1/things/{thing_code}/calendar/
    Get blocked periods for a thing's calendar.
    Owner sees full details, guests see only dates and status.
    """

    permission_classes = [AllowAny]

    def get(self, request, thing_code):
        thing, denied = get_viewable_thing(
            thing_code, viewer_code(request), "Not authorized to view this thing"
        )
        if denied:
            return denied

        # Get blocked periods
        blocked_periods = BookingPeriod.get_blocked_periods(thing_code)

        # Owner (and a PROPRIETARY collection's co-curator, who runs its
        # bookings) sees full details; guests see only dates and status.
        if thing.can_manage(viewer_code(request)):
            # The owner serializer reads requester_code.name per period — pull it
            # in up front so the calendar stays a fixed number of queries
            # regardless of how many bookings it lists.
            blocked_periods = blocked_periods.select_related("requester_code")
            serializer = BookingPeriodOwnerCalendarSerializer(blocked_periods, many=True)
        else:
            serializer = BookingPeriodCalendarSerializer(blocked_periods, many=True)

        return Response(serializer.data, status=status.HTTP_200_OK)


class MyBookingsView(ListAPIView):
    """
    GET /api/v1/my-bookings/
    List all booking requests made by the current user.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = MyBookingSerializer
    pagination_class = StandardResultsPagination

    def get_queryset(self):
        return (
            BookingPeriod.objects.filter(requester_code=self.request.user)
            .select_related("thing_code", "owner_code")
            .order_by("-created")
        )


class OwnerBookingsView(ListAPIView):
    """
    GET /api/v1/owner-bookings/
    List all booking requests for things owned by the current user.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = BookingPeriodSerializer
    pagination_class = StandardResultsPagination

    def get_queryset(self):
        # Bookings on my own things, plus — since 2026-09 — every booking on a
        # thing in a PROPRIETARY collection I curate (owner or co-curator): its
        # curators run its bookings collectively, and `booking.owner_code` is
        # the thing's owner, who in a shared catalogue may be another curator.
        user = self.request.user
        curated = Q(thing_code__collections__mode=Collection.Mode.PROPRIETARY) & (
            Q(thing_code__collections__owner=user) | Q(thing_code__collections__co_owners=user)
        )
        return (
            BookingPeriod.objects.filter(Q(owner_code=user) | curated)
            .select_related("thing_code", "requester_code")
            .prefetch_related("thing_code__collections")
            .distinct()
            .order_by("-created")
        )


class BookingCancelView(APIView):
    """
    POST /api/v1/bookings/{booking_code}/cancel/

    Allows the requester to cancel their own pending booking. For a confirmed
    on-site reservation (RESERVE_THING) **any curator of its collection may
    cancel too** (rule 4) — and only while it hasn't started; everyone who
    didn't cancel is notified. The non-RESERVE branch stays requester-only: a
    curator kills a hold by rejecting it (`BookingActionView`).
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, booking_code):
        booking = get_object_or_404(BookingPeriod, code=booking_code)

        if booking.thing_type == Thing.Type.RESERVE_THING:
            try:
                cancel_reservation(booking, request.user)
            except BookingRequestError as exc:
                return Response({"error": exc.message}, status=exc.status_code)
            return Response({"status": "ok"}, status=status.HTTP_200_OK)

        # Only the requester can cancel
        if booking.requester_code_id != request.user.code:
            return Response(
                {"error": "Not authorized"},
                status=status.HTTP_403_FORBIDDEN,
            )

        if not booking.is_valid():
            return Response(
                {"error": "Booking expired or already processed"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        thing = cancel_booking(booking)

        # A concurrent transition already processed this booking — no-op.
        if thing is None:
            return Response(
                {"error": "Booking expired or already processed"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Invalidate any outstanding RSVP links for this booking
        RSVP.objects.filter(
            target_code=booking_code,
            action__in=[RSVP.Action.BOOKING_ACCEPT, RSVP.Action.BOOKING_REJECT],
        ).delete()

        return Response({"status": "ok"}, status=status.HTTP_200_OK)


class BookingActionView(APIView):
    """
    POST /api/v1/bookings/{booking_code}/accept/
    POST /api/v1/bookings/{booking_code}/reject/

    Allows a manager of the thing — its owner, or a curator of a PROPRIETARY
    collection it sits in — to accept or reject a pending booking via an
    authenticated API call (as an alternative to email RSVP links).
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, booking_code, action):
        booking = get_object_or_404(
            BookingPeriod.objects.select_related("thing_code"), code=booking_code
        )

        # The thing owner, or a PROPRIETARY collection's curator, decides
        if not (
            booking.owner_code_id == request.user.code
            or booking.thing_code.can_manage(request.user.code)
        ):
            return Response(
                {"error": "Not authorized"},
                status=status.HTTP_403_FORBIDDEN,
            )

        if not booking.is_valid():
            return Response(
                {"error": "Booking expired or already processed"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        accepted = action == "accept"
        thing = finalize_booking_decision(booking, accepted=accepted)

        # A concurrent request (double-click, or email link racing this call)
        # already transitioned this booking — the service no-ops and returns None.
        if thing is None:
            return Response(
                {"error": "Booking expired or already processed"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response({"status": "ok"}, status=status.HTTP_200_OK)

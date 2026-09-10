"""
Booking serializers for OIUEEI.
"""

from datetime import date, timedelta

from rest_framework import serializers

from core.models.booking import BookingPeriod
from core.validators import SafeTextField

# Bookings/orders can't be placed more than ~3 months ahead — matches the
# frontend's today+90 cap and the availability horizon (L7).
MAX_BOOKING_HORIZON_DAYS = 90


class BookingPeriodSerializer(serializers.ModelSerializer):
    """Full booking period serializer (for owner view)."""

    thing_code = serializers.CharField(source="thing_code_id")
    thing_headline = serializers.CharField(source="thing_code.headline", read_only=True)
    requester_code = serializers.CharField(source="requester_code_id")
    requester_name = serializers.CharField(source="requester_code.name", read_only=True)
    owner_code = serializers.CharField(source="owner_code_id")
    # Whether accepting this request hands the thing over for good. `thing_type`
    # alone can't answer it: an endless GIFT is given away again and again and
    # transfers nothing, so a client deciding from the type would warn about a
    # transfer that isn't going to happen. The owner-requests page uses it to
    # decide whether accepting needs a confirmation first.
    thing_is_endless = serializers.BooleanField(source="thing_code.is_endless", read_only=True)
    # The group the request belongs to, for the /owner-bookings label: the page
    # now pools requests across every PROPRIETARY collection the viewer curates,
    # so a co-curator of two groups needs to see which one each row is about.
    collection_code = serializers.SerializerMethodField()
    collection_headline = serializers.SerializerMethodField()

    class Meta:
        model = BookingPeriod
        fields = [
            "code",
            "created",
            "thing_code",
            "thing_headline",
            "thing_type",
            "thing_is_endless",
            "collection_code",
            "collection_headline",
            "requester_code",
            "requester_name",
            "requester_email",
            "owner_code",
            "start_date",
            "end_date",
            "status",
            "project_note",
        ]

    def _collection(self, obj):
        # A thing can sit in several collections; this takes the first (the view
        # prefetches `thing_code__collections`, so it costs no extra query). The
        # rare multi-collection thing whose curated group isn't first is a known
        # imprecision, not a correctness bug — the label is orientation only.
        cols = list(obj.thing_code.collections.all())
        return cols[0] if cols else None

    def get_collection_code(self, obj):
        collection = self._collection(obj)
        return collection.code if collection else None

    def get_collection_headline(self, obj):
        collection = self._collection(obj)
        return collection.headline if collection else None


class BookingPeriodCalendarSerializer(serializers.ModelSerializer):
    """Calendar view serializer (limited info for guests)."""

    class Meta:
        model = BookingPeriod
        fields = [
            "start_date",
            "end_date",
            "status",
        ]


class BookingPeriodOwnerCalendarSerializer(serializers.ModelSerializer):
    """Calendar view serializer for owner (includes requester info)."""

    requester_code = serializers.CharField(source="requester_code_id")
    requester_name = serializers.SerializerMethodField()

    class Meta:
        model = BookingPeriod
        fields = [
            "code",
            "created",
            "requester_code",
            "requester_name",
            "start_date",
            "end_date",
            "status",
            "project_note",
        ]

    def get_requester_name(self, obj):
        return obj.requester_code.name or obj.requester_email


class ThingRequestWithDatesSerializer(serializers.Serializer):
    """Serializer for thing request with dates (LEND/RENT/SHARE)."""

    start_date = serializers.DateField()
    end_date = serializers.DateField()

    def validate_start_date(self, value):
        """Validate that start_date is today or in the future."""
        if value < date.today():
            raise serializers.ValidationError("Start date must be today or in the future")
        return value

    def validate(self, data):
        """Validate date range."""
        start_date = data.get("start_date")
        end_date = data.get("end_date")

        if start_date and end_date:
            if end_date < start_date:
                raise serializers.ValidationError(
                    {"end_date": "End date must be on or after start date"}
                )
            horizon = date.today() + timedelta(days=MAX_BOOKING_HORIZON_DAYS)
            if end_date > horizon:
                raise serializers.ValidationError(
                    {"end_date": "Dates can be at most 3 months ahead"}
                )
        return data


class ReservationRequestSerializer(serializers.Serializer):
    """RESERVE_THING request: a pickup date + a length in days, plus an optional
    project note. The real duration cap and the weekday rule are checked in the
    service against the collection (``Collection.reservation_violation``)."""

    start_date = serializers.DateField()
    duration_days = serializers.IntegerField(min_value=1, max_value=7)
    project_note = SafeTextField(max_length=512, required=False, allow_blank=True)

    def validate_start_date(self, value):
        if value < date.today():
            raise serializers.ValidationError("Start date must be today or in the future")
        return value


class MyBookingSerializer(serializers.ModelSerializer):
    """Serializer for user's own booking requests."""

    thing_code = serializers.CharField(source="thing_code_id")
    thing_headline = serializers.CharField(source="thing_code.headline", read_only=True)
    owner_code = serializers.CharField(source="owner_code_id")
    owner_name = serializers.SerializerMethodField()

    class Meta:
        model = BookingPeriod
        fields = [
            "code",
            "created",
            "thing_code",
            "thing_headline",
            "thing_type",
            "owner_code",
            "owner_name",
            "start_date",
            "end_date",
            "status",
            "project_note",
        ]

    def get_owner_name(self, obj):
        # Bare name only — never the email fallback (display_name): this is shown
        # to the requester, a co-member, and L2 forbids leaking a member's email.
        return obj.owner_code.name

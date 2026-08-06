"""
Thing serializers for OIUEEI.
"""

from django.db.models import Count, Prefetch
from rest_framework import serializers

from core.models import Thing
from core.models.booking import BookingPeriod
from core.utils import cloudinary_url
from core.validators import (
    LOCALIZED_TAG_STORAGE,
    ImageIdField,
    LocalizedHeadlineField,
    LocalizedTextField,
    SafeHeadlineField,
    reject_spreadsheet_formula,
)


def optimise_thing_queryset(queryset, *, with_collections=False):
    """Attach the select/prefetch chain every list-of-things view needs so
    ThingComputedFieldsMixin's getters below stay prefetch-aware and N+1-free.

    ``with_collections`` also prefetches ``collections`` — skip it when the
    queryset is already nested inside a collection's own ``Prefetch("things", ...)``
    (avoids a redundant/circular fetch).
    """
    related = ["faq_set", "deal"]
    if with_collections:
        related.insert(0, "collections")
    return (
        queryset.select_related("owner")
        .annotate(_transfer_count=Count("transfers", distinct=True))
        .prefetch_related(
            *related,
            Prefetch(
                "bookings",
                queryset=BookingPeriod.objects.filter(status=BookingPeriod.Status.PENDING),
                to_attr="_pending_bookings",
            ),
            Prefetch(
                "bookings",
                queryset=BookingPeriod.objects.filter(
                    status__in=[
                        BookingPeriod.Status.PENDING,
                        BookingPeriod.Status.ACCEPTED,
                    ]
                )
                # The requester is joined here because this prefetch now also
                # feeds the owner-only `bookings` field, which prints their name.
                # Without it the field would trade one query per card for one per
                # booking — a worse N+1 than the one it removes.
                .select_related("requester_code")
                .order_by("start_date"),
                to_attr="_blocked_periods",
            ),
        )
    )


class ThingComputedFieldsMixin(serializers.Serializer):
    """Computed read-only thing fields shared by ThingSerializer and
    CollectionThingSummarySerializer.

    Every getter here is prefetch-aware — it reuses the ``_pending_bookings``,
    ``_transfer_count``, ``faq_set`` and ``_blocked_periods``
    caches set by the views — so serialising a list of things stays free of N+1
    queries. Fields whose logic genuinely differs between the two serializers
    (``thumbnail_url``) deliberately stay on each
    serializer rather than here.
    """

    owner_name = serializers.SerializerMethodField()
    gallery_urls = serializers.SerializerMethodField()
    pending_booking = serializers.SerializerMethodField()
    bookings = serializers.SerializerMethodField()
    my_pending_booking = serializers.SerializerMethodField()
    pending_questions = serializers.SerializerMethodField()
    transfer_count = serializers.SerializerMethodField()
    available_today = serializers.SerializerMethodField()
    next_available = serializers.SerializerMethodField()

    def get_owner_name(self, obj):
        # Bare name by default — never the email — because this is shown to
        # co-members (and to anonymous visitors on PUBLIC collections) in the
        # community grid, where an email fallback would leak it (L2).
        # Exception: the collection owner already sees co-members' emails
        # (owner-only `invites`), so when the viewer owns the collection being
        # serialised (``parent_collection`` is only set on the collection grid)
        # we fall back to the email for owners who haven't set a name. Standalone
        # thing endpoints have no ``parent_collection`` → email is never exposed.
        if obj.owner.name:
            return obj.owner.name
        request = self.context.get("request")
        collection = self.context.get("parent_collection")
        if (
            request
            and request.user.is_authenticated
            and collection is not None
            and collection.is_owner(request.user.code)
        ):
            return obj.owner.email
        return obj.owner.name

    def get_gallery_urls(self, obj):
        return [cloudinary_url(public_id) for public_id in (obj.gallery or [])]

    def get_pending_booking(self, obj):
        # Use prefetched _pending_bookings if available, otherwise query
        if hasattr(obj, "_pending_bookings"):
            bookings = obj._pending_bookings
            return bookings[0].code if bookings else None
        booking = BookingPeriod.objects.filter(
            thing_code=obj,
            status=BookingPeriod.Status.PENDING,
        ).first()
        return booking.code if booking else None

    def get_bookings(self, obj):
        """The owner's own booking list, served from the prefetch (owner-only).

        This is the same set `GET /things/{code}/calendar/` returns, and it is
        here so the card stops asking for it. `ThingLinkbox` fetched the calendar
        once **per card** for every date-based or TAKEN thing it rendered, so a
        lending library's owner opening their own collection fired one request
        per item — on the page they visit most, from a phone (DESIGN §7). The
        rows were already in memory: `_blocked_periods` is the same PENDING +
        ACCEPTED set, prefetched to compute availability.

        `None` for anyone who isn't the thing's owner — requester names are not
        public — which also tells the client to fall back to fetching, so a
        serializer that hasn't been given a request still behaves as before.
        """
        from core.serializers.booking import BookingPeriodOwnerCalendarSerializer

        request = self.context.get("request")
        if not (request and request.user.is_authenticated and obj.owner_id == request.user.code):
            return None
        periods = (
            obj._blocked_periods
            if hasattr(obj, "_blocked_periods")
            else list(BookingPeriod.get_blocked_periods(obj.code))
        )
        return BookingPeriodOwnerCalendarSerializer(periods, many=True).data

    def get_my_pending_booking(self, obj):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return None
        # Reuse the prefetched PENDING bookings (all requesters) when present.
        if hasattr(obj, "_pending_bookings"):
            for b in obj._pending_bookings:
                if b.requester_code_id == request.user.code:
                    return b.code
            return None
        booking = BookingPeriod.objects.filter(
            thing_code=obj,
            requester_code=request.user,
            status=BookingPeriod.Status.PENDING,
        ).first()
        return booking.code if booking else None

    def get_pending_questions(self, obj):
        # Use prefetched faq_set cache if available
        return sum(1 for faq in obj.faq_set.all() if faq.answer == "" and faq.is_visible)

    def get_transfer_count(self, obj):
        if hasattr(obj, "_transfer_count"):
            return obj._transfer_count
        return obj.transfers.count()

    def _availability_window(self, obj):
        # The collection grid nests things inside a collection's own Prefetch, so it
        # does NOT prefetch ``collections`` — letting availability_window() resolve
        # the rule-setting collection itself would be an N+1 there. It is exactly
        # the collection being rendered, so pass it (``parent_collection`` is only
        # set on that path; standalone thing endpoints prefetch ``collections`` and
        # resolve it for free).
        return obj.availability_window(collection=self.context.get("parent_collection"))

    def get_available_today(self, obj):
        window = self._availability_window(obj)
        return window["available_today"] if window else None

    def get_next_available(self, obj):
        window = self._availability_window(obj)
        return window["next_available"] if window else None


class ThingSerializer(ThingComputedFieldsMixin, serializers.ModelSerializer):
    """Full thing serializer."""

    thumbnail_url = serializers.SerializerMethodField()
    owner = serializers.CharField(source="owner_id")
    faqs = serializers.SerializerMethodField()
    deal = serializers.SlugRelatedField(slug_field="code", many=True, read_only=True)
    collection_code = serializers.SerializerMethodField()
    collection_headline = serializers.SerializerMethodField()
    collection_owner = serializers.SerializerMethodField()
    rental_durations = serializers.SerializerMethodField()
    rental_weekdays = serializers.SerializerMethodField()
    collection_tags = serializers.SerializerMethodField()

    class Meta:
        model = Thing
        fields = [
            "code",
            "type",
            "owner",
            "owner_name",
            "created",
            "headline",
            "description",
            "thumbnail",
            "thumbnail_url",
            "gallery",
            "gallery_urls",
            "tags",
            "collection_tags",
            "status",
            "faqs",
            "fee",
            "availability",
            "location",
            "condition",
            "available_today",
            "next_available",
            "deal",
            "pending_booking",
            "bookings",
            "my_pending_booking",
            "pending_questions",
            "collection_code",
            "collection_headline",
            "collection_owner",
            "rental_durations",
            "rental_weekdays",
            "transfer_count",
            "is_endless",
        ]
        read_only_fields = [
            "code",
            "owner",
            "created",
            "faqs",
            "deal",
        ]

    def get_thumbnail_url(self, obj):
        return cloudinary_url(obj.thumbnail)

    def get_collection_code(self, obj):
        # Use prefetched collections cache if available
        collections = obj.collections.all()
        first = collections[0] if collections else None
        return first.code if first else None

    def get_collection_headline(self, obj):
        collections = obj.collections.all()
        first = collections[0] if collections else None
        return first.headline if first else None

    def get_collection_owner(self, obj):
        collections = obj.collections.all()
        first = collections[0] if collections else None
        return first.owner_id if first else None

    def get_rental_durations(self, obj):
        """Allowed rental lengths (days) from this thing's first collection (#7).
        Used by RequestThingPage to offer the fixed-duration picker for LEND/RENT."""
        collections = obj.collections.all()
        first = collections[0] if collections else None
        return list(first.rental_durations) if first else []

    def get_rental_weekdays(self, obj):
        """Allowed pickup/return weekdays (0=Mon…6=Sun) from the first collection."""
        collections = obj.collections.all()
        first = collections[0] if collections else None
        return list(first.rental_weekdays) if first else []

    def get_faqs(self, obj):
        # Use prefetched faq_set cache if available
        return [faq.code for faq in obj.faq_set.all()]

    def get_collection_tags(self, obj):
        # The tag vocabulary available to this thing — union of its collections'
        # tags. Feeds the tag picker on the edit form without an extra fetch.
        seen = set()
        result = []
        for collection in obj.collections.all():
            for tag in collection.tags or []:
                if tag not in seen:
                    seen.add(tag)
                    result.append(tag)
        return result


class ThingCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating a thing."""

    headline = LocalizedHeadlineField(max_length=64)
    description = LocalizedTextField(max_length=256, required=False, allow_blank=True)
    thumbnail = ImageIdField()
    location = SafeHeadlineField(max_length=32, required=False, allow_blank=True)
    gallery = serializers.ListField(
        child=ImageIdField(allow_blank=False),
        max_length=8,
        required=False,
        allow_empty=True,
    )
    tags = serializers.ListField(
        child=LocalizedHeadlineField(max_length=32, storage_max_length=LOCALIZED_TAG_STORAGE),
        max_length=12,
        required=False,
        allow_empty=True,
    )
    # Non-negative, bounded to the model's 10-digit / 2-decimal range (L7).
    fee = serializers.DecimalField(
        max_digits=10, decimal_places=2, min_value=0, required=False, allow_null=True
    )

    class Meta:
        model = Thing
        fields = [
            "type",
            "headline",
            "description",
            "thumbnail",
            "gallery",
            "tags",
            "fee",
            "availability",
            "location",
            "condition",
            "is_endless",
        ]


class ThingUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating a thing."""

    headline = LocalizedHeadlineField(max_length=64, required=False)
    description = LocalizedTextField(max_length=256, required=False, allow_blank=True)
    thumbnail = ImageIdField()
    location = SafeHeadlineField(max_length=32, required=False, allow_blank=True)
    gallery = serializers.ListField(
        child=ImageIdField(allow_blank=False),
        max_length=8,
        required=False,
        allow_empty=True,
    )
    tags = serializers.ListField(
        child=LocalizedHeadlineField(max_length=32, storage_max_length=LOCALIZED_TAG_STORAGE),
        max_length=12,
        required=False,
        allow_empty=True,
    )
    # Non-negative, bounded to the model's 10-digit / 2-decimal range (L7).
    fee = serializers.DecimalField(
        max_digits=10, decimal_places=2, min_value=0, required=False, allow_null=True
    )

    class Meta:
        model = Thing
        fields = [
            "type",
            "headline",
            "description",
            "thumbnail",
            "gallery",
            "tags",
            "status",
            "fee",
            "availability",
            "location",
            "condition",
            "is_endless",
        ]
        read_only_fields = ["status"]

    def validate_tags(self, value):
        """Each tag must belong to the vocabulary of the thing's collection(s)."""
        if not value:
            return value
        available = set()
        if self.instance is not None:
            for collection in self.instance.collections.all():
                available.update(collection.tags or [])
        invalid = [t for t in value if t not in available]
        if invalid:
            raise serializers.ValidationError(
                f"These tags are not defined by the collection: {invalid}"
            )
        return value


class LocaleDecimalField(serializers.DecimalField):
    """A ``DecimalField`` that also accepts a decimal comma (bulk-CSV only, S9).

    Spanish/Catalan spreadsheet exports write decimals as ``1,5``; a plain
    ``DecimalField`` 400s on that. When the input is a string with exactly one
    ``,`` and no ``.``, the comma is the decimal separator and gets normalised
    to a dot before validation runs. A string carrying **both** ``.`` and
    ``,`` is ambiguous (thousands separator or decimal?) and is rejected
    outright rather than guessed — never guess with money. Anything else
    (already-dotted, an integer, multiple commas with no dot, ...) is left for
    the parent field to accept or reject as it always did.
    """

    def to_internal_value(self, data):
        if isinstance(data, str) and "," in data:
            if "." in data:
                raise serializers.ValidationError(
                    "Ambiguous number: use either a comma or a dot as the decimal "
                    "separator, not both."
                )
            if data.count(",") == 1:
                data = data.replace(",", ".")
        return super().to_internal_value(data)


class ThingBulkRowSerializer(serializers.ModelSerializer):
    """One row of a CSV bulk import (F-9).

    Reuses the project's safe text fields (HTML / line-break / unsafe-scheme
    rejection) and adds a CSV-injection guard on each free-text field. Photos and
    gallery can't be bulk-imported; tags can — a single
    ``|``-separated cell, validated against the collection's vocabulary in the
    view (the serializer has no collection context).
    """

    headline = LocalizedHeadlineField(max_length=64)
    description = LocalizedTextField(max_length=256, required=False, allow_blank=True)
    location = SafeHeadlineField(max_length=32, required=False, allow_blank=True)
    # LocaleDecimalField (not the plain DecimalField the other Thing
    # serializers use): a CSV row is the one path with no NumberInput to
    # normalise a locale decimal comma before it reaches the server (S9).
    fee = LocaleDecimalField(
        max_digits=10, decimal_places=2, min_value=0, required=False, allow_null=True
    )
    tags = serializers.ListField(
        child=LocalizedHeadlineField(max_length=32, storage_max_length=LOCALIZED_TAG_STORAGE),
        max_length=12,
        required=False,
        allow_empty=True,
    )
    # Cover photo public_id. A CSV can't carry binaries, but a ZIP bundle can:
    # the client unzips, uploads each image to Cloudinary, and sends the resulting
    # public_id here (validated path-traversal-safe like the single-create path).
    thumbnail = ImageIdField(required=False, allow_blank=True)

    class Meta:
        model = Thing
        fields = [
            "type",
            "headline",
            "description",
            "fee",
            "availability",
            "location",
            "condition",
            "tags",
            "thumbnail",
            "is_endless",
        ]

    def validate_headline(self, value):
        return reject_spreadsheet_formula(value)

    def validate_description(self, value):
        return reject_spreadsheet_formula(value)

    def validate_location(self, value):
        return reject_spreadsheet_formula(value)

    def validate_tags(self, value):
        # Guard each tag against spreadsheet-formula (CSV) injection, like the
        # other free-text fields. The subset-against-collection check runs in
        # ThingBulkCreateView (the serializer has no collection context).
        return [reject_spreadsheet_formula(tag) for tag in value] if value else value

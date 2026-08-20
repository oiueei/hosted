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

    def _reading_collection(self, obj):
        """The collection this thing is being read *through*, or ``None``.

        Two call sites, two ways of knowing: the collection grid passes the
        collection it is rendering as ``parent_collection``; the thing endpoints
        resolve it per viewer (``ThingSerializer._viewable_collection``, absent
        from the summary serializer). Used to tell the person who published the
        listing apart from a member who contributed to someone else's group.
        """
        collection = self.context.get("parent_collection")
        if collection is not None:
            return collection
        resolver = getattr(self, "_viewable_collection", None)
        return resolver(obj) if resolver else None

    def get_owner_name(self, obj):
        # Withheld from readers with no account when the owner is *not* the
        # person who published the collection — i.e. a member who contributed a
        # thing to someone else's group, which only happens in COMMUNITY mode.
        # That member is a third party exactly like the FAQ asker and the
        # journey's past holders: they consented to a group, not to the open
        # web, and the visibility switch belongs to the curator, not to them.
        # A group's membership stayed legible from the open web through the
        # cards of the things it shares.
        #
        # The curator's own name is *not* withheld: they chose to publish, and
        # `CollectionSerializer.get_owner_name` already serves it to the same
        # reader in the page header — hiding it here would be theatre.
        # Comparing the two owners says exactly that, and needs no mode check.
        #
        # Withheld is `""`, the value a nameless owner already produced, so no
        # client meets a kind of value it did not have to handle. Fail-closed on
        # a request-less context and on a collection we cannot resolve, like
        # `core.serializers.transfer._may_read_names`.
        request = self.context.get("request")
        if not (request and request.user.is_authenticated):
            collection = self._reading_collection(obj)
            if collection is None or collection.owner_id != obj.owner_id:
                return ""
            return obj.owner.name
        # Bare name by default — never the email — because this is shown to
        # co-members in the community grid, where an email fallback would leak
        # it (L2). Exception: the collection owner already sees co-members'
        # emails (owner-only `invites`), so when the viewer owns the collection
        # being serialised (``parent_collection`` is only set on the collection
        # grid) we fall back to the email for owners who haven't set a name.
        # Standalone thing endpoints have no ``parent_collection`` → email is
        # never exposed.
        if obj.owner.name:
            return obj.owner.name
        # Authentication is already guaranteed by the early return above.
        collection = self.context.get("parent_collection")
        if collection is not None and collection.is_owner(request.user.code):
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

    def _viewer_collection_codes(self):
        """Codes of every collection the requesting user owns or belongs to.

        One query per request, cached on the shared serializer context: the
        collection fields below ask this for every thing in a list, and going
        through ``Collection.can_view()`` instead would fire ``is_invited()``
        once per thing per collection — an N+1 on ``/invited-things/``.
        """
        if "_viewer_collection_codes" not in self.context:
            from django.db.models import Q

            from core.models import Collection

            request = self.context.get("request")
            user = getattr(request, "user", None)
            codes = frozenset()
            if user is not None and user.is_authenticated:
                codes = frozenset(
                    Collection.objects.filter(Q(owner=user) | Q(invites=user)).values_list(
                        "code", flat=True
                    )
                )
            self.context["_viewer_collection_codes"] = codes
        return self.context["_viewer_collection_codes"]

    def _viewable_collections(self, obj):
        """The thing's collections **this viewer is allowed to read**, in order.

        A thing can live in several collections at once, and the collection
        fields below used to answer with ``collections.all()[0]`` — whichever the
        DB handed back first, viewable or not. So a drill shared with both a
        private family group and a public neighbourhood one told every reader of
        the public one the name and code of the private one: `/shared` printed it
        on the card, `/things/{code}` used it as the back label for anonymous
        visitors, and following it landed on a 403. `Thing.can_view()` let the
        *thing* through on the strength of the public collection; nothing then
        re-asked the question about the collection it named.

        Mirrors ``Collection.can_view()`` exactly — owner regardless of status,
        never INACTIVE otherwise, then PUBLIC or membership — but reads the
        prefetched rows and one cached code set, so it costs no query per thing.

        A context with no request is internal use (a serializer called directly,
        no viewer to judge): everything is viewable, as before.
        """
        collections = list(obj.collections.all())
        request = self.context.get("request")
        if request is None:
            return collections

        from core.models import Collection

        viewer = request.user.code if request.user.is_authenticated else None
        member_codes = self._viewer_collection_codes()
        return [
            collection
            for collection in collections
            if collection.owner_id == viewer
            or (
                collection.status == Collection.Status.ACTIVE
                and (collection.is_public() or collection.code in member_codes)
            )
        ]

    def _viewable_collection(self, obj):
        """The first collection this viewer may read, or ``None``. Memoised —
        five fields ask for it per thing."""
        if not hasattr(obj, "_viewable_collection_cache"):
            viewable = self._viewable_collections(obj)
            obj._viewable_collection_cache = viewable[0] if viewable else None
        return obj._viewable_collection_cache

    def get_collection_code(self, obj):
        first = self._viewable_collection(obj)
        return first.code if first else None

    def get_collection_headline(self, obj):
        first = self._viewable_collection(obj)
        return first.headline if first else None

    def get_collection_owner(self, obj):
        first = self._viewable_collection(obj)
        return first.owner_id if first else None

    def get_rental_durations(self, obj):
        """Allowed rental lengths (days) from this thing's first collection (#7).
        Used by RequestThingPage to offer the fixed-duration picker for LEND/RENT."""
        first = self._viewable_collection(obj)
        return list(first.rental_durations) if first else []

    def get_rental_weekdays(self, obj):
        """Allowed pickup/return weekdays (0=Mon…6=Sun) from the first collection."""
        first = self._viewable_collection(obj)
        return list(first.rental_weekdays) if first else []

    def get_faqs(self, obj):
        # Use prefetched faq_set cache if available
        return [faq.code for faq in obj.faq_set.all()]

    def get_collection_tags(self, obj):
        # The tag vocabulary available to this thing — union of the collections
        # the viewer may read. Feeds the tag picker on the edit form without an
        # extra fetch. Narrowed for the same reason as the fields above: a label
        # set is weaker evidence than a headline, but it still describes a group
        # the reader has no business seeing. The thing's owner loses nothing —
        # a thing only reaches a collection because its owner added it, which
        # takes ownership or membership either way.
        seen = set()
        result = []
        for collection in self._viewable_collections(obj):
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

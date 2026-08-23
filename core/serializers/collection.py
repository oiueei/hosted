"""
Collection serializers for OIUEEI.
"""

from django.db import transaction
from rest_framework import serializers

from core.models import RSVP, Collection, InvitationProposal, Thing
from core.serializers.thing import ThingComputedFieldsMixin
from core.utils import asset_url, doc_asset_url
from core.validators import (
    LOCALIZED_TAG_STORAGE,
    ImageIdField,
    LocalizedHeadlineField,
    LocalizedTextField,
    SafeTextField,
)

# The thing types a collection's allowlist may name. PROPRIETARY and COMMUNITY
# take the same set — mode decides WHO may add a thing (owner only, or any
# member), never WHICH types are on offer.
ALLOWED_THING_TYPES = (
    Thing.Type.GIFT_THING,
    Thing.Type.SELL_THING,
    Thing.Type.RENT_THING,
    Thing.Type.LEND_THING,
)


class CollectionThingSummarySerializer(ThingComputedFieldsMixin, serializers.ModelSerializer):
    """Lightweight thing serializer for collection listings."""

    owner = serializers.CharField(source="owner_id")
    thumbnail_url = serializers.SerializerMethodField()
    deal = serializers.SlugRelatedField(slug_field="code", many=True, read_only=True)

    class Meta:
        model = Thing
        fields = [
            "code",
            "type",
            "owner",
            "owner_name",
            "headline",
            "description",
            "status",
            "fee",
            "availability",
            "available_today",
            "next_available",
            "location",
            "condition",
            "thumbnail_url",
            "gallery_urls",
            "tags",
            "pending_booking",
            "bookings",
            "my_pending_booking",
            "pending_questions",
            "transfer_count",
            "deal",
            "created",
        ]

    def get_thumbnail_url(self, obj):
        return asset_url(obj.thumbnail) if obj.thumbnail else None


class CollectionListSerializer(serializers.ListSerializer):
    """List serializer that batch-loads the owner-only ``pending_invites``.

    ``pending_invites`` come from the RSVP table keyed by ``target_code`` (a
    plain CharField, not a FK — so there is no relation to ``prefetch_related``).
    Serialising a list of an owner's collections would otherwise fire one RSVP
    query per collection (N+1). Here we fetch them all in a single query and
    stash them on the shared context for the child serializer to read.
    """

    def to_representation(self, data):
        instances = list(data)
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            owned_codes = [c.code for c in instances if c.owner_id == request.user.code]
            if owned_codes:
                by_code = {}
                rows = RSVP.objects.filter(
                    action=RSVP.Action.COLLECTION_INVITE,
                    target_code__in=owned_codes,
                ).values("target_code", "user_code_id", "user_email")
                for row in rows:
                    by_code.setdefault(row["target_code"], []).append(
                        {"code": row["user_code_id"], "email": row["user_email"]}
                    )
                self.context["_pending_invites_by_code"] = by_code
        return super().to_representation(instances)


class CollectionSerializer(serializers.ModelSerializer):
    """Full collection serializer."""

    owner = serializers.CharField(source="owner_id")
    owner_name = serializers.SerializerMethodField()
    thumbnail_url = serializers.SerializerMethodField()
    welcome_doc_url = serializers.SerializerMethodField()
    things = serializers.SerializerMethodField()
    invites = serializers.SerializerMethodField()
    pending_invites = serializers.SerializerMethodField()
    is_member = serializers.SerializerMethodField()
    is_digest_muted = serializers.SerializerMethodField()
    pending_proposals = serializers.SerializerMethodField()
    is_paused = serializers.BooleanField(read_only=True)

    class Meta:
        model = Collection
        list_serializer_class = CollectionListSerializer
        fields = [
            "code",
            "owner",
            "owner_name",
            "created",
            "headline",
            "description",
            "status",
            "mode",
            "visibility",
            "digest_frequency",
            "allow_member_proposals",
            "language",
            "allowed_thing_types",
            "rental_durations",
            "rental_weekdays",
            "deposit_policy",
            "tags",
            "thumbnail",
            "thumbnail_url",
            "welcome_doc",
            "welcome_doc_url",
            "pause_message",
            "is_paused",
            "things",
            "invites",
            "pending_invites",
            "is_member",
            "is_digest_muted",
            "pending_proposals",
        ]
        read_only_fields = [
            "code",
            "owner",
            "created",
            "is_paused",
            "things",
            "invites",
            "pending_invites",
            "is_member",
            "is_digest_muted",
            "pending_proposals",
        ]

    def get_owner_name(self, obj):
        # Bare name, not display_name — guests see this, so the email fallback
        # would leak the owner's address (L2).
        return obj.owner.name

    def get_thumbnail_url(self, obj):
        return asset_url(obj.thumbnail) if obj.thumbnail else None

    def get_welcome_doc_url(self, obj):
        return doc_asset_url(obj.welcome_doc) if obj.welcome_doc else None

    def get_things(self, obj):
        request = self.context.get("request")
        ctx = {**self.context, "parent_collection": obj}
        is_owner = bool(
            request and request.user.is_authenticated and obj.is_owner(request.user.code)
        )
        things = obj.things.all()
        # Non-owners (including anonymous visitors on a PUBLIC collection) never
        # see INACTIVE things; only skip the filter for internal, request-less use.
        # Filtered in Python (not .exclude()) so the prefetched M2M cache is reused
        # instead of firing a fresh query per thing (N+1 on home + anon collection
        # detail).
        if request and not is_owner:
            things = [t for t in things if t.status != Thing.Status.INACTIVE]
        return CollectionThingSummarySerializer(things, many=True, context=ctx).data

    def _requester_is_owner(self, obj):
        request = self.context.get("request")
        return bool(request and request.user.is_authenticated and obj.is_owner(request.user.code))

    def get_is_member(self, obj):
        # True when the requester is an invited member (not the owner). Reads the
        # prefetched invites so it adds no query. Drives the "Leave the group" button.
        request = self.context.get("request")
        if not (request and request.user.is_authenticated) or self._requester_is_owner(obj):
            return False
        return any(u.code == request.user.code for u in obj.invites.all())

    def get_pending_proposals(self, obj):
        """Members' pending recommendations — **owner only**.

        These name a person who has not been contacted and does not know they
        were suggested, and they carry the proposer's private note. Nobody but
        the person who has to decide sees them.
        """
        if not self._requester_is_owner(obj):
            return []
        # Prefetched by `_optimise_collection_queryset` for signed-in viewers;
        # the fallback keeps a request-less or unoptimised caller working.
        pending = getattr(obj, "_pending_proposals", None)
        if pending is None:
            pending = obj.invitation_proposals.filter(
                status=InvitationProposal.Status.PENDING
            ).select_related("proposer")
        return [
            {
                "code": p.code,
                "email": p.email,
                "note": p.note,
                "proposer_name": p.proposer.name,
                "created": p.created,
            }
            for p in pending
        ]

    def get_is_digest_muted(self, obj):
        # Whether *this* viewer has silenced this collection's digest. Only
        # meaningful for a member — the owner never receives their own digest —
        # so everyone else gets False and no toggle is rendered for them.
        request = self.context.get("request")
        if not (request and request.user.is_authenticated) or self._requester_is_owner(obj):
            return False
        return any(u.code == request.user.code for u in obj.digest_muted.all())

    def get_invites(self, obj):
        members = obj.invites.all()
        if self._requester_is_owner(obj):
            # In a COMMUNITY collection the owner also sees each member's optional
            # age range and postal code (owner-only, never public). Other modes
            # and non-owners never receive them.
            community = obj.is_community()
            result = []
            for u in members:
                member = {"code": u.code, "email": u.email, "name": u.name}
                if community:
                    member["age_range"] = u.age_range
                    member["postal_code"] = u.postal_code
                result.append(member)
            return result
        # Co-members' emails are owner-only (L2); logged-in guests get only
        # code + name. An ANONYMOUS reader of a PUBLIC collection gets codes
        # alone — the member count survives for the card, but real names of a
        # group's members don't belong to the open web (early-bird hardening).
        request = self.context.get("request")
        if not (request and request.user.is_authenticated):
            return [{"code": u.code} for u in members]
        return [{"code": u.code, "name": u.name} for u in members]

    def get_pending_invites(self, obj):
        # Pending invitees and their emails are owner-management data only.
        if not self._requester_is_owner(obj):
            return []
        # Reuse the batch the list serializer pre-loaded, if present (avoids the
        # per-collection N+1 when serialising a list); fall back to a single
        # query for the detail endpoint / direct use.
        cache = self.context.get("_pending_invites_by_code")
        if cache is not None:
            return cache.get(obj.code, [])
        rsvps = RSVP.objects.filter(
            action=RSVP.Action.COLLECTION_INVITE,
            target_code=obj.code,
        ).values("user_code_id", "user_email")
        return [{"code": r["user_code_id"], "email": r["user_email"]} for r in rsvps]


class CollectionCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating a collection."""

    headline = LocalizedHeadlineField(max_length=64)
    description = LocalizedTextField(max_length=256, required=False, allow_blank=True)
    thumbnail = ImageIdField(required=False, allow_blank=True)
    # The welcome PDF is a storage key like any other asset — same
    # path-traversal-safe validation.
    welcome_doc = ImageIdField(required=False, allow_blank=True)
    tags = serializers.ListField(
        child=LocalizedHeadlineField(max_length=32, storage_max_length=LOCALIZED_TAG_STORAGE),
        max_length=12,
        required=False,
        allow_empty=True,
    )
    rental_durations = serializers.ListField(
        child=serializers.IntegerField(min_value=1, max_value=90),
        max_length=8,
        required=False,
        allow_empty=True,
    )
    rental_weekdays = serializers.ListField(
        child=serializers.IntegerField(min_value=0, max_value=6),
        max_length=7,
        required=False,
        allow_empty=True,
    )
    # Localized like every other owner text (D5): a deposit policy that could
    # only be written in one language would be the single piece of group prose
    # that a bilingual group cannot say twice. 256 visible per language, 1024
    # stored — the same arithmetic as `description`.
    deposit_policy = LocalizedTextField(max_length=256, required=False, allow_blank=True)

    class Meta:
        model = Collection
        fields = [
            "headline",
            "description",
            "mode",
            "visibility",
            "digest_frequency",
            "allow_member_proposals",
            "language",
            "allowed_thing_types",
            "rental_durations",
            "rental_weekdays",
            "deposit_policy",
            "tags",
            "thumbnail",
            "welcome_doc",
        ]

    def validate_tags(self, value):
        return _normalize_tags(value)

    def validate_rental_durations(self, value):
        return sorted(set(value))

    def validate_rental_weekdays(self, value):
        return sorted(set(value))

    def validate(self, attrs):
        # Default visibility follows the mode when the client doesn't set it:
        # community collections are born PUBLIC, proprietary ones PRIVATE. The
        # owner can override either way via the toggle.
        if not attrs.get("visibility"):
            mode = attrs.get("mode", Collection.Mode.PROPRIETARY)
            attrs["visibility"] = (
                Collection.Visibility.PUBLIC
                if mode == Collection.Mode.COMMUNITY
                else Collection.Visibility.PRIVATE
            )
        _validate_allowed_thing_types(attrs.get("allowed_thing_types", []))
        return attrs


def _normalize_tags(tags):
    """Trim each tag, drop empties, and dedupe case-insensitively (first wins).

    Used by both collection serializers so the owner-defined tag vocabulary is
    always clean. The ListField (max_length=12) caps the raw count and
    LocalizedHeadlineField rejects HTML / over-length labels before this runs (a
    label may be a per-language map, in which case each language is checked).
    """
    seen = set()
    result = []
    for raw in tags:
        label = (raw or "").strip()
        if not label:
            continue
        key = label.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(label)
    return result


def _validate_allowed_thing_types(allowed_thing_types):
    """Validate the allowed_thing_types list when non-empty.

    Empty list means "no restriction" — accepted in any mode (preserves the
    pre-feature behaviour and keeps the API tolerant for non-form callers).
    The "user must pick at least one" rule is enforced in the create/edit
    form on the frontend, where it belongs as a UX nudge.
    """
    invalid = [t for t in allowed_thing_types if t not in ALLOWED_THING_TYPES]
    if invalid:
        raise serializers.ValidationError(f"These types are not allowed: {invalid}")


class CollectionUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating a collection."""

    headline = LocalizedHeadlineField(max_length=64, required=False)
    description = LocalizedTextField(max_length=256, required=False, allow_blank=True)
    thumbnail = ImageIdField(required=False, allow_blank=True)
    # The welcome PDF is a storage key like any other asset — same
    # path-traversal-safe validation.
    welcome_doc = ImageIdField(required=False, allow_blank=True)
    pause_message = SafeTextField(max_length=256, required=False, allow_blank=True)
    tags = serializers.ListField(
        child=LocalizedHeadlineField(max_length=32, storage_max_length=LOCALIZED_TAG_STORAGE),
        max_length=12,
        required=False,
        allow_empty=True,
    )
    rental_durations = serializers.ListField(
        child=serializers.IntegerField(min_value=1, max_value=90),
        max_length=8,
        required=False,
        allow_empty=True,
    )
    rental_weekdays = serializers.ListField(
        child=serializers.IntegerField(min_value=0, max_value=6),
        max_length=7,
        required=False,
        allow_empty=True,
    )
    # Localized like every other owner text (D5): a deposit policy that could
    # only be written in one language would be the single piece of group prose
    # that a bilingual group cannot say twice. 256 visible per language, 1024
    # stored — the same arithmetic as `description`.
    deposit_policy = LocalizedTextField(max_length=256, required=False, allow_blank=True)

    class Meta:
        model = Collection
        fields = [
            "headline",
            "description",
            "status",
            "mode",
            "visibility",
            "digest_frequency",
            "allow_member_proposals",
            "language",
            "allowed_thing_types",
            "rental_durations",
            "rental_weekdays",
            "deposit_policy",
            "tags",
            "thumbnail",
            "welcome_doc",
            "pause_message",
        ]

    def validate_rental_durations(self, value):
        return sorted(set(value))

    def validate_rental_weekdays(self, value):
        return sorted(set(value))

    def validate(self, attrs):
        instance = self.instance
        allowed_thing_types = attrs.get(
            "allowed_thing_types",
            instance.allowed_thing_types if instance else [],
        )
        _validate_allowed_thing_types(allowed_thing_types)
        # Orphan check: if this is an update narrowing the list, every existing
        # thing currently in the collection must keep a valid slot in the new
        # list. Otherwise the rule would become incoherent ("type X is not
        # allowed but the collection contains 3 of them").
        if instance is not None and "allowed_thing_types" in attrs and allowed_thing_types:
            existing_types = set(instance.things.values_list("type", flat=True))
            orphaned = sorted(existing_types - set(allowed_thing_types))
            if orphaned:
                raise serializers.ValidationError(
                    "Cannot restrict the allowed types: existing things would be"
                    f" orphaned (types: {orphaned}). Remove them first."
                )
        return attrs

    def validate_tags(self, value):
        return _normalize_tags(value)

    def update(self, instance, validated_data):
        """Cascade-strip: when the owner removes a tag from the collection's
        vocabulary, drop it from every thing in the collection that still had it
        (tags are cosmetic, so we silently clean up rather than block the edit)."""
        new_tags = validated_data.get("tags")
        old_tags = list(instance.tags or [])
        # Atomic so the collection edit and the cascade land together — a failure
        # mid-cascade must not leave the vocabulary changed but some things still
        # carrying a removed tag. bulk_update writes the strip in one query.
        with transaction.atomic():
            collection = super().update(instance, validated_data)
            if new_tags is not None:
                removed = set(old_tags) - set(new_tags)
                if removed:
                    stripped = []
                    for thing in collection.things.all():
                        if any(t in removed for t in (thing.tags or [])):
                            thing.tags = [t for t in thing.tags if t not in removed]
                            stripped.append(thing)
                    if stripped:
                        Thing.objects.bulk_update(stripped, ["tags"])
        return collection


class CollectionInviteSerializer(serializers.Serializer):
    """Serializer for inviting a user to a collection."""

    email = serializers.EmailField(max_length=64)


class CollectionProposeInviteSerializer(serializers.Serializer):
    """A member suggesting somebody to the collection's owner.

    The `note` is the proposer's word to the owner — the thing that makes the
    approval a decision rather than a guess ("she's my downstairs neighbour",
    "he's paid the subs"). Optional, `SafeTextField` like every other free-text
    field, and never shown to the person being proposed.
    """

    email = serializers.EmailField(max_length=64)
    note = SafeTextField(max_length=256, required=False, allow_blank=True)


class CollectionAddThingSerializer(serializers.Serializer):
    """Serializer for adding a thing to a collection."""

    thing_code = serializers.CharField(max_length=6)


class CollectionRemoveThingSerializer(serializers.Serializer):
    """Serializer for removing a thing from a collection."""

    thing_code = serializers.CharField(max_length=6)


class CollectionRemoveInviteSerializer(serializers.Serializer):
    """Serializer for removing a user from a collection's invite list."""

    user_code = serializers.CharField(max_length=6)


class CollectionBroadcastSerializer(serializers.Serializer):
    """Serializer for broadcasting a message to collection invitees.

    The subject is auto-generated ("Hey! {collection}"); only the message is
    user-provided.
    """

    message = SafeTextField(max_length=256)

"""
Transfer serializers for OIUEEI.
"""

from rest_framework import serializers

from core.models.transfer import ThingTransfer


def _may_read_names(context):
    """Whether this reader may be told who has held the thing.

    The journey names **third parties** — every member the thing has passed
    through — and a thing sitting in a PUBLIC collection is readable with no
    account at all. So a group's membership was legible from the open web by
    reading the loan chain of one of its objects, which is the exposure
    `CollectionSerializer.get_invites` already closed on the collection itself
    ("real names of a group's members don't belong to the open web"). Same
    people, different endpoint.

    Withheld means each field returns **its own** empty value — `""` for the
    per-hop names, `None` for the aggregates — so no client meets a kind of
    value it did not already have to handle (a deleted account produced both
    long before this).

    Fail-closed on a missing request, like `get_invites`: request-less use
    (internal callers) withholds too, so a call site that forgets to pass the
    context cannot leak.
    """
    request = context.get("request")
    return bool(request and request.user.is_authenticated)


class ThingTransferSerializer(serializers.ModelSerializer):
    """Individual transfer record."""

    from_user = serializers.CharField(source="from_user_id", allow_null=True)
    from_user_name = serializers.SerializerMethodField()
    to_user = serializers.CharField(source="to_user_id", allow_null=True)
    to_user_name = serializers.SerializerMethodField()

    class Meta:
        model = ThingTransfer
        fields = [
            "code",
            "from_user",
            "from_user_name",
            "to_user",
            "to_user_name",
            "lent_date",
            "returned_date",
            "auto_closed",
        ]

    def get_from_user_name(self, obj):
        # Bare name, not display_name — the journey is shown community-wide, so
        # the email fallback would leak addresses (L2). A null user is a deleted
        # account (SET_NULL, right to erasure): the hop stays, the name goes —
        # the frontend renders its own "former member" label for the empty value.
        # Signed-out readers get that same empty value (see `_may_read_names`).
        if not _may_read_names(self.context):
            return ""
        return obj.from_user.name if obj.from_user else ""

    def get_to_user_name(self, obj):
        if not _may_read_names(self.context):
            return ""
        return obj.to_user.name if obj.to_user else ""


class ThingTransferStatsSerializer(serializers.Serializer):
    """Aggregated transfer stats for a thing."""

    total_transfers = serializers.IntegerField()
    unique_homes = serializers.IntegerField()
    current_holder = serializers.CharField(allow_null=True)
    current_holder_name = serializers.SerializerMethodField()
    original_owner = serializers.CharField(allow_null=True)
    original_owner_name = serializers.SerializerMethodField()
    transfers = ThingTransferSerializer(many=True)

    # The two names the view hands us, gated by the same rule as the per-hop
    # ones. Method fields rather than plain CharFields so the whole "who may be
    # told a name" question lives in this module, in one place, instead of half
    # here and half in the view — the shape that lets the two drift.
    # `None` is what these already carried for "nobody to name".

    def get_current_holder_name(self, obj):
        if not _may_read_names(self.context):
            return None
        return obj.get("current_holder_name")

    def get_original_owner_name(self, obj):
        if not _may_read_names(self.context):
            return None
        return obj.get("original_owner_name")

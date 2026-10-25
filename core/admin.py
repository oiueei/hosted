"""
Django Admin configuration for OIUEEI.
"""

from django import forms
from django.contrib import admin

from core.models import (
    FAQ,
    RSVP,
    Braaanding,
    Collection,
    DeviceDay,
    Report,
    Theeeme,
    Thing,
    User,
)
from core.models.booking import BookingPeriod


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ["code", "email", "name", "created"]
    search_fields = ["code", "email", "name"]

    def get_form(self, request, obj=None, **kwargs):
        # about is a CharField (max_length=2000, not TextField — see
        # core/models/CLAUDE.md), so the admin's default widget is a
        # single-line <input>, which silently strips every pasted newline
        # out of a multi-line Markdown bio — the API/TextArea save path
        # preserves them fine; only this default admin widget doesn't.
        # formfield_overrides can't target one field by name, so override the
        # widget per-request here instead.
        kwargs["widgets"] = {"about": forms.Textarea}
        return super().get_form(request, obj, **kwargs)


@admin.register(Collection)
class CollectionAdmin(admin.ModelAdmin):
    list_display = [
        "code",
        "headline",
        "owner",
        "status",
        "thing_count",
        "capacity_unblocked",
    ]
    search_fields = ["code", "headline"]
    # `capacity_unblocked` is filterable and editable in the list: lifting the
    # mass-upload ceiling for one collection is the documented superuser
    # unblock, and it should not require opening the change form to find it.
    list_filter = ["status", "capacity_unblocked", "things_alarm_sent", "invites_alarm_sent"]
    list_editable = ["capacity_unblocked"]
    # The share token is a bearer credential: anyone holding it can join the
    # collection. Read-only here not to hide it — a superuser reaches the row
    # either way — but because the default form made it *writable*, and a
    # hand-typed value silently bypasses `generate_share_token`'s 22 URL-safe
    # characters of entropy. Rotating and revoking belong to the owner, through
    # CollectionShareLinkView, which always mints a real one.
    readonly_fields = ["share_token"]

    # The kind never changes after creation (the serializer refuses it too): editing
    # it here would leave the verb list, the things' verbs and the links outside
    # their kind. It stays choosable when a collection is added.
    def get_readonly_fields(self, request, obj=None):
        fields = super().get_readonly_fields(request, obj)
        return [*fields, "kind"] if obj is not None else fields

    @admin.display(description="Things")
    def thing_count(self, obj):
        """The number the capacity guards compare against."""
        return obj.things.count()


@admin.register(Thing)
class ThingAdmin(admin.ModelAdmin):
    list_display = [
        "code",
        "headline",
        "owner",
        "type",
        "status",
    ]
    search_fields = ["code", "headline"]
    list_filter = ["type", "status"]


@admin.register(FAQ)
class FAQAdmin(admin.ModelAdmin):
    list_display = ["code", "question", "thing", "is_visible"]
    search_fields = ["code", "question"]
    list_filter = ["is_visible"]


@admin.register(RSVP)
class RSVPAdmin(admin.ModelAdmin):
    list_display = ["code", "user_email", "user_code", "created"]
    search_fields = ["code", "user_email"]


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    # Platform-moderation log: how many reports landed, on what, and when.
    # The reporter column is staff-only here and never surfaced to owners.
    list_display = ["code", "thing_headline", "thing", "reporter", "created"]
    search_fields = ["code", "thing_headline", "thing__code", "reporter__code", "reporter__email"]
    list_filter = ["created"]
    readonly_fields = ["code", "thing", "thing_headline", "reporter", "created"]


@admin.register(Theeeme)
class TheeemeAdmin(admin.ModelAdmin):
    list_display = ["code", "name", "color_01", "color_02", "color_03", "color_04", "color_05"]
    search_fields = ["code", "name"]


@admin.register(Braaanding)
class BraaandingAdmin(admin.ModelAdmin):
    """The app's own palette: one row, edited here and nowhere else.

    Nothing is added or deleted (there is exactly one palette, and the pages and
    the emails read it), and a palette that fails the contrast the twelve
    collection palettes meet is refused on save (`Braaanding.clean`).
    """

    list_display = ["code", "color_01", "color_02", "color_03", "color_04", "color_05", "color_06"]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(BookingPeriod)
class BookingPeriodAdmin(admin.ModelAdmin):
    list_display = [
        "code",
        "thing_code",
        "thing_type",
        "requester_code",
        "owner_code",
        "status",
        "created",
    ]
    search_fields = ["code", "requester_email"]
    list_filter = ["status", "thing_type"]


@admin.register(DeviceDay)
class DeviceDayAdmin(admin.ModelAdmin):
    # A daily count with nobody in it: to be read, never edited by hand.
    list_display = ["date", "device", "metric", "count"]
    list_filter = ["device", "metric"]
    date_hierarchy = "date"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

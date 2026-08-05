# Removes SHARE_THING, the share-only collection flag and the weekly newsletter
# that rode on it. Last of the three type removals (0121 wishes, 0122 swaps),
# leaving the catalogue at the four validated types: GIFT, SELL, RENT, LEND.
#
# Same policy as its two predecessors: existing share things are HIDDEN, not
# deleted, and keep ``type="SHARE_THING"`` so restoring the type later leaves
# only `status` to undo.
#
# BOOKING_UNAVAILABLE goes with it. It told a requester the thing had gone to
# someone else, and was only ever emitted when accepting an ownership-transferring
# hold auto-declined its siblings — which only SHARE (and the already-removed
# SWAP) did. The existing rows are deleted along with their renderer; a hold on
# the remaining four types is never auto-declined.
#
# ``newsletter_enabled`` is dropped rather than kept dormant: the newsletter's
# second block listed ownership changes, which no remaining type produces. A
# newsletter for a lending library is a different feature needing different copy —
# meanwhile the weekly digest (``digest_frequency``) is untouched and already
# works on any collection.

from django.db import migrations, models


def hide_share_things(apps, schema_editor):
    Thing = apps.get_model("core", "Thing")
    Thing.objects.filter(type="SHARE_THING").update(status="INACTIVE")


def drop_unavailable_notifications(apps, schema_editor):
    InAppNotification = apps.get_model("core", "InAppNotification")
    InAppNotification.objects.filter(type="BOOKING_UNAVAILABLE").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0122_remove_swap_thing"),
    ]

    operations = [
        migrations.RunPython(hide_share_things, migrations.RunPython.noop),
        migrations.RunPython(drop_unavailable_notifications, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="collection",
            name="is_share",
        ),
        migrations.RemoveField(
            model_name="collection",
            name="newsletter_enabled",
        ),
        migrations.AlterField(
            model_name="inappnotification",
            name="type",
            field=models.CharField(
                choices=[
                    ("BROADCAST", "Broadcast"),
                    ("COLLECTION_DELETED", "Collection Deleted"),
                    ("COLLECTION_REVOKED", "Collection Revoked"),
                    ("BOOKING_ACCEPTED", "Booking Accepted"),
                    ("BOOKING_REJECTED", "Booking Rejected"),
                    ("BOOKING_REQUESTED", "Booking Requested"),
                    ("FAQ_QUESTION", "Faq Question"),
                    ("FAQ_ANSWERED", "Faq Answered"),
                    ("FAQ_HIDDEN", "Faq Hidden"),
                    ("INVITE_REJECTED", "Invite Rejected"),
                    ("MEMBER_LEFT", "Member Left"),
                    ("THING_REPORTED", "Thing Reported"),
                ],
                max_length=32,
            ),
        ),
        # max_length stays 11 even though the longest remaining type is 10 chars:
        # narrowing it would truncate the SHARE_THING / SWAP_THING / WISH_THING
        # rows that 0121–0123 deliberately kept.
        migrations.AlterField(
            model_name="thing",
            name="type",
            field=models.CharField(
                choices=[
                    ("GIFT_THING", "Gift Thing"),
                    ("SELL_THING", "Sell Thing"),
                    ("RENT_THING", "Rent Thing"),
                    ("LEND_THING", "Lend Thing"),
                ],
                default="GIFT_THING",
                max_length=11,
            ),
        ),
    ]

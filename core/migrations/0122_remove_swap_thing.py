# Removes SWAP_THING and the swap-collection machinery: the offered-things M2M
# that carried a proposal's counter-offer, and the two Collection flags that made
# a collection swap-only (``is_swap``) and gated proposing (``swap_minimum_items``).
#
# Same policy as 0121: existing swap things are HIDDEN, not deleted, and keep
# ``type="SWAP_THING"`` so restoring the type later leaves only `status` to undo.
# What does NOT survive is each pending proposal's counter-offer — dropping the
# M2M drops ``booking_offered_things`` with it. That is deliberate (the removal
# was specified as a full extirpation), and it is why the reverse of this
# migration gives back the columns but not their contents.
#
# The SWAP_REQUESTED notifications are deleted: they ask the owner to decide on a
# proposal whose offered items no longer exist anywhere.

from django.db import migrations, models


def hide_swap_things(apps, schema_editor):
    Thing = apps.get_model("core", "Thing")
    Thing.objects.filter(type="SWAP_THING").update(status="INACTIVE")


def drop_swap_notifications(apps, schema_editor):
    InAppNotification = apps.get_model("core", "InAppNotification")
    InAppNotification.objects.filter(type="SWAP_REQUESTED").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0121_remove_wish_thing"),
    ]

    operations = [
        migrations.RunPython(hide_swap_things, migrations.RunPython.noop),
        migrations.RunPython(drop_swap_notifications, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="bookingperiod",
            name="offered_things",
        ),
        migrations.RemoveField(
            model_name="collection",
            name="is_swap",
        ),
        migrations.RemoveField(
            model_name="collection",
            name="swap_minimum_items",
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
                    ("BOOKING_UNAVAILABLE", "Booking Unavailable"),
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
        # max_length stays 11 for SHARE_THING (see 0121).
        migrations.AlterField(
            model_name="thing",
            name="type",
            field=models.CharField(
                choices=[
                    ("GIFT_THING", "Gift Thing"),
                    ("SELL_THING", "Sell Thing"),
                    ("RENT_THING", "Rent Thing"),
                    ("LEND_THING", "Lend Thing"),
                    ("SHARE_THING", "Share Thing"),
                ],
                default="GIFT_THING",
                max_length=11,
            ),
        ),
    ]

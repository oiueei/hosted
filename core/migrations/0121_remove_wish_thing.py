# Removes WISH_THING and the structured-answer layer built on top of it
# (the WishResponse table, its three views and its three in-app notifications).
#
# Existing wishes are HIDDEN, not deleted: a wish is content a member wrote, and
# a deployment that has real ones would otherwise lose them silently on migrate.
# They keep ``type="WISH_THING"`` — a value no longer in Thing.Type.choices, which
# Django only enforces on validation, never on read — so restoring the type later
# brings them back with `status` the only thing to undo. Their owner meanwhile
# sees them under "inactive things" with an untranslated type label; nobody else
# sees them at all.
#
# The WISH_* notifications ARE deleted: they are dismissible, ephemeral inbox rows
# whose frontend renderer is going away in the same commit, so leaving them would
# strand unreadable banners in people's inboxes.

from django.db import migrations, models


def hide_wishes(apps, schema_editor):
    Thing = apps.get_model("core", "Thing")
    Thing.objects.filter(type="WISH_THING").update(status="INACTIVE")


def drop_wish_notifications(apps, schema_editor):
    InAppNotification = apps.get_model("core", "InAppNotification")
    InAppNotification.objects.filter(
        type__in=["WISH_POSTED", "WISH_RESPONSE", "WISH_ACCEPTED"]
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0120_alter_faq_questioner_alter_rsvp_action_and_more"),
    ]

    operations = [
        migrations.RunPython(hide_wishes, migrations.RunPython.noop),
        migrations.RunPython(drop_wish_notifications, migrations.RunPython.noop),
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
                    ("SWAP_REQUESTED", "Swap Requested"),
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
        # max_length stays 11: SHARE_THING is 11 chars and still exists. Narrowing
        # it to 10 would truncate rows on PostgreSQL.
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
                    ("SWAP_THING", "Swap Thing"),
                ],
                default="GIFT_THING",
                max_length=11,
            ),
        ),
        migrations.DeleteModel(
            name="WishResponse",
        ),
    ]

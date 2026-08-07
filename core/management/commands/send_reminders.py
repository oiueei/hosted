"""
Management command to send daily reminder emails.

Sends reminders for:
- Booking returns due tomorrow (end_date = tomorrow) — to **both** sides: the
  owner, who is expecting the thing back, and the borrower, who has to carry it
  there. Only the owner used to be told, which left the one person with
  something to do hearing nothing.

Run daily via Heroku Scheduler.
"""

from datetime import date, timedelta

from django.core.management.base import BaseCommand

from core.models.booking import BookingPeriod
from core.services.email_service import (
    _thing_url,
    send_return_due_email,
    send_return_reminder_email,
)


class Command(BaseCommand):
    help = "Send daily reminder emails for bookings"

    def handle(self, *args, **options):
        tomorrow = date.today() + timedelta(days=1)
        total = 0

        # 1. Booking return reminders (end_date = tomorrow)
        return_bookings = BookingPeriod.objects.filter(
            end_date=tomorrow,
            status=BookingPeriod.Status.ACCEPTED,
        ).select_related("thing_code__owner", "requester_code")

        for booking in return_bookings:
            thing = booking.thing_code
            requester = booking.requester_code
            # One failing recipient must not cost the other their reminder, nor
            # the rest of the run theirs — same reasoning as send_digests.
            for send in (
                lambda: send_return_reminder_email(
                    requester_name=requester.display_name,
                    thing_headline=thing.headline,
                    end_date=booking.end_date,
                    owner_email=thing.owner.email,
                ),
                lambda: send_return_due_email(
                    owner_name=thing.owner.display_name,
                    thing_headline=thing.headline,
                    end_date=booking.end_date,
                    requester_email=requester.email,
                    thing_url=_thing_url(thing),
                ),
            ):
                try:
                    send()
                    total += 1
                except Exception as exc:  # noqa: BLE001 — best-effort fan-out
                    self.stderr.write(
                        self.style.WARNING(f"Reminder failed for booking {booking.code}: {exc}")
                    )

        self.stdout.write(self.style.SUCCESS(f"Sent {total} reminder emails"))

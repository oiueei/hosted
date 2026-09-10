"""
Management command to send daily reminder emails.

Sends reminders for:
- Booking returns due tomorrow (end_date = tomorrow) — to **both** sides: the
  owner, who is expecting the thing back, and the borrower, who has to carry it
  there. Only the owner used to be told, which left the one person with
  something to do hearing nothing. RESERVE_THING is excluded here — nothing is
  carried anywhere.
- On-site reservations starting tomorrow (start_date = tomorrow) — to the
  member who booked the slot. A reservation can be booked up to a year out and
  auto-confirms, so nothing reaches the member between the confirmation and the
  day; a no-show costs a real slot.

Run daily via Heroku Scheduler.
"""

from datetime import date, timedelta

from django.core.management.base import BaseCommand

from core.models.booking import BookingPeriod
from core.models.thing import Thing
from core.services.email_service import (
    send_reservation_reminder_email,
    send_return_due_email,
    send_return_reminder_email,
)


class Command(BaseCommand):
    help = "Send daily reminder emails for bookings"

    def handle(self, *args, **options):
        tomorrow = date.today() + timedelta(days=1)
        total = 0

        # 1. Booking return reminders (end_date = tomorrow). RESERVE_THING is
        # excluded: nothing is carried anywhere, so "tomorrow you take it back"
        # is nonsense for an on-site reservation.
        return_bookings = (
            BookingPeriod.objects.filter(
                end_date=tomorrow,
                status=BookingPeriod.Status.ACCEPTED,
            )
            .exclude(thing_type=Thing.Type.RESERVE_THING)
            .select_related("thing_code__owner", "requester_code")
        )

        for booking in return_bookings:
            thing = booking.thing_code
            requester = booking.requester_code
            # One failing recipient must not cost the other their reminder, nor
            # the rest of the run theirs — same reasoning as send_digests.
            for send in (
                lambda: send_return_reminder_email(
                    requester_name=requester.display_name,
                    thing=thing,
                    end_date=booking.end_date,
                    owner_email=thing.owner.email,
                ),
                lambda: send_return_due_email(
                    owner_name=thing.owner.display_name,
                    thing=thing,
                    end_date=booking.end_date,
                    requester_email=requester.email,
                ),
            ):
                try:
                    send()
                    total += 1
                except Exception as exc:  # noqa: BLE001 — best-effort fan-out
                    self.stderr.write(
                        self.style.WARNING(f"Reminder failed for booking {booking.code}: {exc}")
                    )

        # 2. On-site reservation arrival reminders (start_date = tomorrow). The
        # member auto-confirmed weeks or months ago; this is the only nudge.
        arrival_reservations = BookingPeriod.objects.filter(
            thing_type=Thing.Type.RESERVE_THING,
            start_date=tomorrow,
            status=BookingPeriod.Status.ACCEPTED,
        ).select_related("thing_code", "requester_code")

        for booking in arrival_reservations:
            try:
                send_reservation_reminder_email(
                    requester_email=booking.requester_code.email,
                    thing=booking.thing_code,
                    booking=booking,
                )
                total += 1
            except Exception as exc:  # noqa: BLE001 — best-effort fan-out
                self.stderr.write(
                    self.style.WARNING(f"Reminder failed for booking {booking.code}: {exc}")
                )

        self.stdout.write(self.style.SUCCESS(f"Sent {total} reminder emails"))

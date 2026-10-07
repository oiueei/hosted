"""
Management command to send daily reminder emails.

Sends reminders for:
- Booking returns due tomorrow (end_date = tomorrow) — to **both** sides: the
  owner, who is expecting the thing back, and the borrower, who has to carry it
  there. Only the owner used to be told, which left the one person with
  something to do hearing nothing. RESERVE_THING is excluded here — nothing is
  carried anywhere. A single-day loan (start_date == end_date, tomorrow) is
  excluded too: its "return" reminder is the pickup one, the same day said
  twice.
- On-site reservations starting tomorrow (start_date = tomorrow) — to the
  member who booked the slot. A reservation can be booked up to a year out and
  auto-confirms, so nothing reaches the member between the confirmation and the
  day; a no-show costs a real slot.
- Lend/rent pickups starting tomorrow (start_date = tomorrow, LEND/RENT) — to
  **both** sides again: the borrower, who has to be somewhere at a time
  (`send_pickup_due_email`), and the owner, who has to have the thing ready
  (`send_pickup_reminder_email`). The only pickup email before this was the
  acceptance, sent when the dates were agreed — weeks can pass before the day.
  RESERVE has its own arrival reminder above; GIFT/SELL have no dates.

Run daily via Heroku Scheduler.
"""

from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.db.models import F

from core.models.booking import BookingPeriod
from core.models.thing import Thing
from core.services.email_service import (
    send_pickup_due_email,
    send_pickup_reminder_email,
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
        # is nonsense for an on-site reservation. A single-day loan (start ==
        # end, tomorrow) is left to the pickup block below — one reminder per
        # person about the one day, not two.
        return_bookings = (
            BookingPeriod.objects.filter(
                end_date=tomorrow,
                status=BookingPeriod.Status.ACCEPTED,
            )
            .exclude(thing_type=Thing.Type.RESERVE_THING)
            .exclude(start_date=F("end_date"))
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

        # 3. Pickup reminders (start_date = tomorrow, LEND/RENT). The handover
        # itself: both sides are nudged the day before, the same per-recipient
        # swallow as the return block so one broken send costs nobody theirs.
        pickup_bookings = BookingPeriod.objects.filter(
            start_date=tomorrow,
            status=BookingPeriod.Status.ACCEPTED,
            thing_type__in=[Thing.Type.LEND_THING, Thing.Type.RENT_THING],
        ).select_related("thing_code__owner", "requester_code")

        for booking in pickup_bookings:
            thing = booking.thing_code
            requester = booking.requester_code
            for send in (
                lambda: send_pickup_due_email(
                    owner_name=thing.owner.display_name,
                    thing=thing,
                    start_date=booking.start_date,
                    requester_email=requester.email,
                ),
                lambda: send_pickup_reminder_email(
                    requester_name=requester.display_name,
                    thing=thing,
                    start_date=booking.start_date,
                    owner_email=thing.owner.email,
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

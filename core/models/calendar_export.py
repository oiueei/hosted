"""Which reservations a collection has already handed to a calendar export.

The collection calendar CSV download (``CollectionCalendarExportView``) is
**incremental**: each download carries only the date-based reservations that
haven't gone out before, then records that they have. This table is that
record — one row per ``(collection, booking)`` a download has already
delivered.

Per collection, **not** per curator: a PROPRIETARY collection's curators run
its catalogue together, so once anyone has exported a reservation it is done
for the group. It is also why the state lives here rather than as a flag on
``BookingPeriod`` — a thing can sit in two collections, and each keeps its own
watermark on the same booking.

The rows cascade with either side: deleting the collection or the booking
takes its marks with it, which is the right behaviour — a booking that no
longer exists cannot be re-exported anyway.
"""

from django.db import models
from django.utils import timezone

from core.utils import generate_id


class CalendarExportMark(models.Model):
    """One reservation, already delivered to this collection's calendar export."""

    code = models.CharField(max_length=6, primary_key=True, default=generate_id)
    collection = models.ForeignKey(
        "Collection",
        on_delete=models.CASCADE,
        related_name="calendar_export_marks",
    )
    booking = models.ForeignKey(
        "BookingPeriod",
        on_delete=models.CASCADE,
        related_name="calendar_export_marks",
    )
    exported_at = models.DateTimeField(default=timezone.now)

    class Meta:
        app_label = "core"
        db_table = "calendar_export_marks"
        constraints = [
            models.UniqueConstraint(
                fields=["collection", "booking"],
                name="uniq_calendar_export_collection_booking",
            )
        ]

    def __str__(self):
        return f"{self.collection_id}/{self.booking_id}"

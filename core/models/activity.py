"""First-party daily-activity record — one row per user per day they were active.

The app keeps no session/analytics concept, so returns and retention are otherwise
unanswerable. This is deliberately the smallest thing that answers them: a
``(user, date)`` row, written at most once per user per day by
``core.middleware.DailyActivityMiddleware`` (guarded by a cache key so it's one DB
write per user per day, not per request).

Powers WAU/MAU per role, creator/guest return counts, and "guests who never come
back after their first visit". It records *less* than the web server logs already
hold and never leaves our DB (DESIGN §9).
"""

from django.db import models

from core.utils import generate_id

from .user import User


class DailyActivity(models.Model):
    code = models.CharField(max_length=6, primary_key=True, default=generate_id)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="daily_activity")
    date = models.DateField()

    class Meta:
        db_table = "daily_activity"
        ordering = ["-date"]
        constraints = [
            models.UniqueConstraint(fields=["user", "date"], name="unique_daily_activity_per_day")
        ]
        # Range scans over "everyone active since <cutoff>" (WAU/MAU) filter by date.
        indexes = [models.Index(fields=["date"])]

    def __str__(self):
        return f"{self.user_id} active {self.date}"


class DeviceDay(models.Model):
    """A daily count, per kind of device, of signed-in people and of form saves.

    Answers one product question — how much of the use, and above all how many
    collection/thing saves, come from a phone rather than from anything else —
    without holding anyone. A row is ``(date, device, metric, count)``: no user,
    no ``User-Agent``, nothing that could be traced back to a person. Written by
    ``core.middleware.DailyActivityMiddleware`` from headers the request already
    carries, and never leaves our DB (DESIGN §9, aggregate counters).

    ``device`` has two values on purpose: ``MOBILE`` and ``OTHER`` (a tablet counts
    as ``OTHER``). With two groups the answer is reliable; with three it would not
    be, because an iPad presents itself as a desktop Safari.

    ``PEOPLE`` counts signed-in people per day and device (one person on a phone
    and a laptop the same day counts once in each); ``FORM_SAVES`` counts every
    successful create or edit of a collection or a thing.

    There is no retention period, and the table is not in ``purge_expired_data``,
    the data export or account erasure: it holds no personal data to expire, export
    or erase.
    """

    MOBILE = "MOBILE"
    OTHER = "OTHER"
    DEVICE_CHOICES = [(MOBILE, "Mobile"), (OTHER, "Other")]

    PEOPLE = "PEOPLE"
    FORM_SAVES = "FORM_SAVES"
    METRIC_CHOICES = [(PEOPLE, "People"), (FORM_SAVES, "Form saves")]

    code = models.CharField(max_length=6, primary_key=True, default=generate_id)
    date = models.DateField()
    device = models.CharField(max_length=8, choices=DEVICE_CHOICES)
    metric = models.CharField(max_length=16, choices=METRIC_CHOICES)
    count = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "device_day"
        ordering = ["-date", "device", "metric"]
        constraints = [
            models.UniqueConstraint(
                fields=["date", "device", "metric"], name="unique_device_day_metric"
            )
        ]
        indexes = [models.Index(fields=["date"])]

    def __str__(self):
        return f"{self.date} {self.device} {self.metric}: {self.count}"

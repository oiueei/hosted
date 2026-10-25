"""The app's own palette.

Everything that is not a collection's page — Home, the account pages, the login
door, the legal text, the 404, and every email — is painted with this palette,
which no curator can pick. It is a table of its own, with one row, and **not** a
row of `theeemes`: that table is the selector the collections choose from and the
pool a new collection draws its palette from at random, so a palette stored there
could reach both.

Its colours are hexadecimal, not HDS token names, and an operator edits them in
the Django admin without touching code. The page receives them as the six CSS
variables `--color-braaanding-01` … `--color-braaanding-06` (`config.urls.spa_index`
writes them into the HTML it serves), and the emails read the same row.

Because no test can see values that live in the database, the contrast the twelve
collection palettes must meet is checked here, when a palette is saved
(`clean`), and the admin refuses one that fails.
"""

import time

from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.db.models.signals import post_delete, post_save

from core.models.theeeme import KORO_CHOICES
from core.services.palette_contrast import HEX_RE, contrast_failures

# The one row's primary key. A fixed code rather than a generated one: there is
# only ever this row, and the migration, the admin and `braaanding()` all name it.
BRAAANDING_CODE = "OIUEEI"

# What the migration seeds, and what `braaanding()` answers if the row is somehow
# missing (a database flushed by hand), so a page and an email still paint.
DEFAULT_COLORS = {
    "color_01": "#191919",
    "color_02": "#F4E5DD",
    "color_03": "#D77452",
    "color_04": "#191919",
    "color_05": "#191919",
    "color_06": "#FAFAFA",
}
DEFAULT_KORO = "basic"

COLOR_FIELDS = tuple(DEFAULT_COLORS)
# How long a worker keeps the palette it read. The cache lives in each process's own
# memory, not in `CACHES['default']`: every page the app serves reads the palette, and
# the shared cache is a table, so reading it there would spend a query per page view
# on routes that promise to ask the database nothing (`core.throttles`, `spa_index`).
# The price is that another worker keeps the old colours for up to this long after an
# edit in the admin; the process that saved the row forgets at once.
CACHE_SECONDS = 60
_cached = {"palette": None, "expires": 0.0}

_hex_validator = RegexValidator(HEX_RE, "Use a colour like #RRGGBB.")


def _hex_field(role):
    return models.CharField(
        max_length=7,
        validators=[_hex_validator],
        default=DEFAULT_COLORS[role],
        help_text="#RRGGBB",
    )


class Braaanding(models.Model):
    """The app's palette: six hex colours and a koro. One row, edited in the admin."""

    code = models.CharField(max_length=6, primary_key=True, default=BRAAANDING_CODE)
    color_01 = _hex_field("color_01")
    color_02 = _hex_field("color_02")
    color_03 = _hex_field("color_03")
    color_04 = _hex_field("color_04")
    color_05 = _hex_field("color_05")
    color_06 = _hex_field("color_06")
    koro = models.CharField(max_length=9, choices=KORO_CHOICES, default=DEFAULT_KORO)

    class Meta:
        app_label = "core"
        db_table = "braaanding"
        verbose_name = "Braaanding"
        verbose_name_plural = "Braaanding"

    def __str__(self):
        return "The app's palette"

    @property
    def colors(self):
        return {role: getattr(self, role) for role in COLOR_FIELDS}

    def clean(self):
        """Refuse a palette that would paint unreadable text.

        Skipped for a colour that already failed its own format check: the form
        shows that error, and a contrast of "red" would only add noise.
        """
        super().clean()
        colors = self.colors
        if not all(HEX_RE.match(value or "") for value in colors.values()):
            return
        failures = contrast_failures(colors)
        if failures:
            raise ValidationError(
                ["This palette is not readable enough to paint the app with:", *failures]
            )


def braaanding():
    """The app's palette as `{"color_01": "#…", …, "koro": "basic"}`.

    Kept in this process's memory for `CACHE_SECONDS` and dropped whenever the row
    is saved or deleted, so a page view costs no query once a worker has read it.
    With no row (a database flushed by hand) the seeded values answer, so a page
    and an email still paint.
    """
    palette = _cached["palette"]
    if palette is not None and time.monotonic() < _cached["expires"]:
        return dict(palette)

    row = Braaanding.objects.filter(pk=BRAAANDING_CODE).first()
    palette = (
        {**row.colors, "koro": row.koro}
        if row is not None
        else {**DEFAULT_COLORS, "koro": DEFAULT_KORO}
    )
    _cached["palette"] = palette
    _cached["expires"] = time.monotonic() + CACHE_SECONDS
    return dict(palette)


def forget_braaanding():
    """Drop the palette this process remembers (on every save, and between tests)."""
    _cached["palette"] = None
    _cached["expires"] = 0.0


def _forget_braaanding(**_kwargs):
    forget_braaanding()


post_save.connect(_forget_braaanding, sender=Braaanding)
post_delete.connect(_forget_braaanding, sender=Braaanding)

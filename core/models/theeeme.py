"""
Theeeme model for OIUEEI.
"""

import random

from django.db import OperationalError, ProgrammingError, models

from core.utils import generate_id

# The Koros wave types, shared by every palette that carries one.
KORO_CHOICES = [
    ("basic", "Basic"),
    ("beat", "Beat"),
    ("calm", "Calm"),
    ("pulse", "Pulse"),
    ("vibration", "Vibration"),
    ("wave", "Wave"),
]

# Bussi — the documented default palette (seeded in migration 0036). Used only as
# a last-resort fallback when the Theeeme table is somehow empty.
DEFAULT_THEEEME_CODE = "BUU331"


def random_theeeme():
    """Pick a random *existing* theeeme code for a new collection's palette.

    Reads the live Theeeme table rather than a hardcoded list, so removing a
    theeeme can never make creating a collection roll a dangling FK (a 1-in-N
    IntegrityError). Falls back to the default code if the table is empty — or
    missing entirely: Django's system checks instantiate models (evaluating this
    default) before migrations have run on a fresh environment, e.g.
    `makemigrations --check` on a bare CI checkout.
    """
    try:
        codes = list(Theeeme.objects.values_list("code", flat=True))
    except (OperationalError, ProgrammingError):
        return DEFAULT_THEEEME_CODE
    return random.choice(codes) if codes else DEFAULT_THEEEME_CODE


class Theeeme(models.Model):
    """
    A color palette theme for collections.
    Colors are HDS token names (e.g. "bus", "copper", "suomenlinna-light").
    """

    code = models.CharField(max_length=6, primary_key=True, default=generate_id)
    name = models.CharField(max_length=16, default="")
    color_01 = models.CharField(max_length=32)
    color_02 = models.CharField(max_length=32)
    color_03 = models.CharField(max_length=32)
    color_04 = models.CharField(max_length=32)
    color_05 = models.CharField(max_length=32)
    color_06 = models.CharField(max_length=32)

    class Meta:
        app_label = "core"
        db_table = "theeemes"

    def __str__(self):
        return self.code

"""
User model for OIUEEI.
"""

import random
from datetime import date

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager
from django.db import OperationalError, ProgrammingError, models

from core.models.language import Language
from core.utils import generate_id

# Bussi — the documented default palette (seeded in migration 0036). Used only as
# a last-resort fallback when the Theeeme table is somehow empty.
_DEFAULT_THEEEME_CODE = "BUU331"


def _random_theeeme():
    """Pick a random *existing* theeeme code for a new user's default palette.

    Reads the live Theeeme table rather than a hardcoded list, so removing a
    theeeme can never make user creation roll a dangling FK (a 1-in-N
    IntegrityError). Falls back to the default code if the table is empty —
    or missing entirely: Django's auth system check instantiates User()
    (evaluating this default) before migrations have run on a fresh
    environment, e.g. `makemigrations --check` on a bare CI checkout.
    """
    from core.models.theeeme import Theeeme

    try:
        codes = list(Theeeme.objects.values_list("code", flat=True))
    except (OperationalError, ProgrammingError):
        return _DEFAULT_THEEEME_CODE
    return random.choice(codes) if codes else _DEFAULT_THEEEME_CODE


class UserManager(BaseUserManager):
    """Custom manager for User model."""

    def create_user(self, email, password=None, **extra_fields):
        """Create and return a regular user."""
        if not email:
            raise ValueError("Email is required")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, **extra_fields):
        """Create and return a superuser."""
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self.create_user(email, **extra_fields)


class User(AbstractBaseUser):
    """
    Custom User model with 6-character alphanumeric ID.
    Uses magic link authentication (no password).
    """

    KORO_CHOICES = [
        ("basic", "Basic"),
        ("beat", "Beat"),
        ("calm", "Calm"),
        ("pulse", "Pulse"),
        ("vibration", "Vibration"),
        ("wave", "Wave"),
    ]

    class AgeRange(models.TextChoices):
        # Birth-year generations (2026-07 switch from age brackets — a birth
        # year never goes stale, an age bracket did).
        PRE_1946 = "PRE_1946", "1945 or earlier"
        BOOMER = "BOOMER", "Boomers (1946-1964)"
        GEN_X = "GEN_X", "Generation X (1965-1980)"
        GEN_Y = "GEN_Y", "Millennials (1981-1996)"
        GEN_Z = "GEN_Z", "Generation Z (1997-2012)"
        GEN_A = "GEN_A", "Generation Alpha (2013-2024)"
        GEN_B = "GEN_B", "Generation Beta (2025-2039)"

    code = models.CharField(max_length=6, primary_key=True, default=generate_id)
    email = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=32, blank=True, default="")
    created = models.DateField(default=date.today)
    last_activity = models.DateField(null=True, blank=True, default=None)
    # The day we last told this person their account had gone quiet, so the
    # grace period has somewhere to be counted from. Cleared the moment they
    # come back (see `update_last_activity`): a warning that was answered must
    # stop counting, or returning would not save them — which is the one thing
    # the email promises.
    inactivity_notified = models.DateField(null=True, blank=True, default=None)
    headline = models.CharField(max_length=64, blank=True, default="")
    about = models.CharField(max_length=2000, blank=True, default="")
    photo = models.CharField(max_length=255, blank=True, default="")
    koro = models.CharField(max_length=9, choices=KORO_CHOICES, default="basic")
    theeeme = models.ForeignKey(
        "Theeeme",
        on_delete=models.PROTECT,
        to_field="code",
        db_column="user_theeeme",
        related_name="users",
        default=_random_theeeme,
    )

    # Notification preferences (see core/services/email_service.py categories).
    # Activity (Cat. 2) defaults ON — transactional, expected.
    #
    # News (Cat. 3 — the per-collection digest) also defaults ON, which is only
    # defensible because of the second, narrower control beside it:
    # `Collection.digest_muted` lets a member silence one group without giving up
    # the booking and question emails they want. DESIGN §6 forbids making the
    # exit harder than the entrance, not sensible defaults — and the exit here is
    # one link in the footer of the very email being complained about.
    #
    # It defaulted OFF until the 2026-08 design round, which is why the digest
    # reached almost nobody: the owner had to find a buried per-collection
    # setting AND every reader had to have opted in to a switch labelled
    # "optional".
    notify_activity = models.BooleanField(default=True)
    notify_news = models.BooleanField(default=True)

    # Optional demographics. Per member they're shared only with the owner of a
    # COMMUNITY collection (on the guests page); in aggregate they appear in any
    # collection owner's stats CSV. Never public. Both default empty.
    age_range = models.CharField(max_length=8, choices=AgeRange.choices, blank=True, default="")
    postal_code = models.CharField(max_length=10, blank=True, default="")
    # The language this user's own email is written in. Blank = inherit (the
    # collection's language, else the deployment default). Strongest link in the
    # hierarchy — see email_service.resolve_email_language.
    language = models.CharField(max_length=2, choices=Language.choices, blank=True, default="")

    # Required for Django auth
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        app_label = "core"
        db_table = "users"

    def __str__(self):
        return f"{self.code} ({self.email})"

    @property
    def display_name(self):
        """Human-facing name: the chosen name, falling back to the email."""
        return self.name or self.email

    def has_perm(self, perm, obj=None):
        return self.is_superuser

    def has_module_perms(self, app_label):
        return self.is_superuser

    def update_last_activity(self):
        """Update the user's last activity date.

        Coming back also cancels any standing inactivity warning. That is the
        whole promise of the email — "signing in once is enough to keep it" — so
        a grace period that kept running would delete somebody for doing exactly
        what they were asked.
        """
        self.last_activity = date.today()
        fields = ["last_activity"]
        if self.inactivity_notified is not None:
            self.inactivity_notified = None
            fields.append("inactivity_notified")
        self.save(update_fields=fields)

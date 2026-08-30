"""Write the CORS rules the browser needs in order to upload to the bucket.

**The one setup step that lives on the bucket rather than in a config var.**
Everything else a deployment needs to store an asset is a setting; this is state
on the store itself, and until it is written every upload fails in the browser
on the preflight while the server sees nothing wrong at all — the ticket was
issued, the credentials are right, the signature is right, and the file never
leaves the laptop.

It is also invisible from the outside, which is what makes it worth a command
rather than a line in a README. Photos already in the bucket go on loading,
because reading one is an ``<img src>`` and not a cross-origin request; only
writing needs permission. A deployment can therefore look completely healthy and
accept no new photo at all. (That is not hypothetical — it is how this was
found.)

Run it once per bucket, and again whenever the origins change::

    python manage.py set_bucket_cors --origin https://www.example.com
    heroku run --app <app> "python manage.py set_bucket_cors --origin https://www.example.com"

Quote the inner command on Heroku, or its CLI eats ``--origin``.

With no ``--origin`` it falls back to ``CORS_ALLOWED_ORIGINS`` — where a
deployment has already written down the domains it answers for; in development
that is localhost, in production it is the config var of the same name.

**No domain is written down in this file, and none ever should be.** The origins
belong to whoever runs the deployment. A default naming somebody's site is a
default that quietly configures the wrong bucket.

The rules themselves are in ``core.services.storage`` (``cors_rules``), next to
the ``presign_upload`` that decides which headers they have to allow.
"""

from urllib.parse import urlparse

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core.services import storage


class Command(BaseCommand):
    help = "Write the bucket's CORS rules so browsers may upload to it."

    def add_arguments(self, parser):
        parser.add_argument(
            "--origin",
            action="append",
            dest="origins",
            default=[],
            help=(
                "An origin allowed to upload, e.g. https://www.example.com. "
                "Repeatable. Defaults to CORS_ALLOWED_ORIGINS."
            ),
        )
        parser.add_argument(
            "--max-age",
            type=int,
            default=storage.CORS_MAX_AGE_SECONDS,
            help=(
                "How long a browser may cache the preflight, in seconds "
                f"(default {storage.CORS_MAX_AGE_SECONDS})."
            ),
        )
        parser.add_argument(
            "--replace",
            action="store_true",
            help="Overwrite rules that are already there and are not the ones this would write.",
        )
        parser.add_argument(
            "--show",
            action="store_true",
            help="Print the bucket's current rules and change nothing.",
        )

    def handle(self, *args, **options):
        bucket = self._bucket()
        current = self._current()

        if options["show"]:
            self._print_rules(f"Current CORS rules on {bucket}", current)
            return

        origins = self._origins(options["origins"])
        wanted = storage.cors_rules(origins, max_age=options["max_age"])

        self.stdout.write(f"Bucket: {bucket}")
        self._print_rules("Currently", current)
        self._print_rules("Writing", wanted)

        if self._same(current, wanted):
            self.stdout.write(self.style.SUCCESS("Already exactly these rules — nothing to do."))
            return

        # Somebody else's rules are not ours to throw away: this replaces the
        # whole configuration (S3 has no partial update), so a bucket shared with
        # another application would lose that application's permissions without a
        # word. `--replace` is the acknowledgement, and an unconfigured bucket —
        # the case this command exists for — never asks for it.
        if current and not options["replace"]:
            raise CommandError(
                "This bucket already has CORS rules, and they are not the ones above. "
                "Writing replaces the whole configuration, so re-run with --replace "
                "if those rules are yours to overwrite."
            )

        try:
            storage.put_cors(wanted)
        except Exception as exc:  # noqa: BLE001 — surface any storage/config error cleanly
            raise CommandError(f"Could not write the CORS rules: {exc}") from exc

        # Read back rather than trust the 200: this command's whole job is to
        # leave the bucket in a known state, and some S3-compatible stores accept
        # a field they then do not keep (Hetzner drops `Cache-Control` from a POST
        # policy, which is why uploads are a PUT at all).
        applied = self._current()
        self._print_rules("Now on the bucket", applied)
        if not self._same(applied, wanted):
            raise CommandError(
                "The store accepted the rules but did not store them as written — "
                "compare the two lists above."
            )
        self.stdout.write(
            self.style.SUCCESS(
                "CORS rules written. Uploads from those origins will now get past the preflight."
            )
        )

    def _bucket(self):
        """The configured bucket, or a clean error naming what is unset."""
        try:
            return storage.bucket_name()
        except Exception as exc:  # noqa: BLE001
            raise CommandError(str(exc)) from exc

    def _current(self):
        try:
            return storage.get_cors()
        except Exception as exc:  # noqa: BLE001
            raise CommandError(f"Could not read the bucket's CORS rules: {exc}") from exc

    def _origins(self, given):
        """The origins to allow — the flag, else the setting — each validated.

        Falling back to ``CORS_ALLOWED_ORIGINS`` is not a convenience: it is the
        list a deployment has *already* had to get right for its own API, so the
        two cannot drift into disagreeing about which sites this app is.
        """
        origins = given or list(getattr(settings, "CORS_ALLOWED_ORIGINS", []))
        if not origins:
            raise CommandError(
                "No origins to allow. Pass --origin https://your-domain, or set "
                "CORS_ALLOWED_ORIGINS for this deployment."
            )
        return [self._origin(origin) for origin in origins]

    @staticmethod
    def _origin(value):
        """Scheme and host, exactly as a browser sends them in ``Origin``.

        A trailing slash is the mistake this catches, and it is worth catching
        because it fails *silently*: ``https://example.com/`` is never equal to
        the ``Origin`` header a browser sends, so the rule matches nothing and
        the upload goes on being refused with the bucket now looking configured.
        Pasting a URL out of the address bar is how it gets there, so the bare
        slash is normalised rather than refused. A real path is a different
        mistake — it means somebody thinks CORS matches on paths — and is worth a
        loud stop.
        """
        parsed = urlparse((value or "").strip())
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise CommandError(
                f"Not an origin: {value!r}. It needs a scheme and a host, "
                "e.g. https://www.example.com"
            )
        if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
            raise CommandError(
                f"An origin is a scheme and a host, with no path: {value!r}. "
                "CORS never matches on the path."
            )
        return f"{parsed.scheme}://{parsed.netloc}"

    @staticmethod
    def _same(current, wanted):
        """Whether the bucket already holds these rules, ignoring cosmetics.

        Compared field by field rather than with ``==`` because a store is free
        to answer with keys nobody set (``ExposeHeaders: []``, an ``ID``) and to
        return header names in whatever case it stored them. Neither changes what
        the browser is allowed to do, and treating either as a difference would
        make this command rewrite the same rules forever.
        """
        if len(current) != len(wanted):
            return False
        for mine, theirs in zip(current, wanted, strict=True):
            if sorted(mine.get("AllowedOrigins", [])) != sorted(theirs["AllowedOrigins"]):
                return False
            if sorted(mine.get("AllowedMethods", [])) != sorted(theirs["AllowedMethods"]):
                return False
            if sorted(h.lower() for h in mine.get("AllowedHeaders", [])) != sorted(
                h.lower() for h in theirs["AllowedHeaders"]
            ):
                return False
            if mine.get("MaxAgeSeconds") != theirs["MaxAgeSeconds"]:
                return False
        return True

    def _print_rules(self, label, rules):
        if not rules:
            self.stdout.write(f"{label}: none.")
            return
        self.stdout.write(f"{label}:")
        for rule in rules:
            self.stdout.write(f"  origins: {', '.join(rule.get('AllowedOrigins', [])) or '—'}")
            self.stdout.write(f"  methods: {', '.join(rule.get('AllowedMethods', [])) or '—'}")
            self.stdout.write(f"  headers: {', '.join(rule.get('AllowedHeaders', [])) or '—'}")
            self.stdout.write(f"  preflight cached: {rule.get('MaxAgeSeconds', '—')}s")

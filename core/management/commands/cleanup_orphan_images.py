"""
Management command to delete orphaned images from object storage (#9).

An "orphan" is an image that was uploaded (a ticketed direct-to-bucket upload
from a form) but whose form was never submitted, so no DB row ever referenced
its key. Deleting on record-delete is already handled by
``core.services.asset_cleanup``; this command catches the *other* leak —
uploads that never became a record at all.

**Dry-run is the default.** It only lists what it *would* delete; pass
``--commit`` to actually delete. Safe to run on Heroku:

    heroku run --app <app> "python manage.py cleanup_orphan_images"           # dry-run
    heroku run --app <app> "python manage.py cleanup_orphan_images --commit"  # delete

(Quote the inner command so the Heroku CLI doesn't eat ``--commit``.)

Safety rails:
- Cross-references **every** DB asset field — Thing.thumbnail + Thing.gallery,
  User.photo, Collection.thumbnail and Collection.welcome_doc — so anything in use
  is kept. The welcome PDF matters here: it is an object in the same tree as the
  photos, so it turns up in this sweep like any of them, and a missing
  cross-reference would delete a live document. The default ``--prefix`` is the
  whole ``oiueei/`` tree, so welcome docs living in ``oiueei/documents/`` (S4)
  need no special handling — they are swept alongside every other subfolder and
  cross-referenced the same way.
- Never touches the ``oiueei/seed/`` folder (the demo's shared image pool).
- Only considers assets **older than --min-age-hours** (default 24h) so an
  in-flight upload mid-form isn't mistaken for an orphan, and **younger than
  --max-age-days** (default 30) so it stays a recent-window sweep. Run it
  regularly (e.g. weekly) and every orphan is caught within its window.

The age comes from S3's ``LastModified``, which for these objects is the upload
time: a key is random, written once and never rewritten, so nothing else can
move it. That is the property the window relies on, and the reason an object
must never be overwritten in place — doing so would reset its clock and hide it
from the sweep for another day.

**On checksums**, because this is the command that would break first: botocore
1.36 began sending ``x-amz-checksum-crc32`` by default and dropping
``Content-MD5``, and several S3-compatible providers reject it on
``DeleteObjects`` specifically. Verified accepted on Hetzner with botocore
1.43.78. If a future bump makes deletion start failing here, the rescue is in
``core/services/storage.py``, not in this file.
"""

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone as dj_timezone

from core.models import Collection, Thing, User
from core.services import storage

SEED_PREFIX = storage.SEED_PREFIX
DELETE_BATCH = 100


class Command(BaseCommand):
    help = "Delete orphaned images from object storage (uploaded but never saved to a record)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--commit",
            action="store_true",
            help="Actually delete. Without this flag the command is a dry-run (default).",
        )
        parser.add_argument(
            "--min-age-hours",
            type=int,
            default=24,
            help="Ignore assets newer than this — skips in-flight uploads (default 24h).",
        )
        parser.add_argument(
            "--max-age-days",
            type=int,
            default=30,
            help="Ignore assets older than this — keeps it a recent-window sweep (default 30).",
        )
        parser.add_argument(
            "--prefix",
            default="oiueei/",
            help="Storage key prefix to scan (default 'oiueei/').",
        )

    def handle(self, *args, **options):
        commit = options["commit"]
        prefix = options["prefix"]
        now = dj_timezone.now()
        min_age = dj_timezone.timedelta(hours=options["min_age_hours"])
        max_age = dj_timezone.timedelta(days=options["max_age_days"])

        referenced = self._referenced_keys()
        self.stdout.write(f"Referenced by DB: {len(referenced)} image(s).")

        scanned = seed_skipped = referenced_skipped = window_skipped = 0
        orphans = []

        for asset in self._iter_objects(prefix):
            scanned += 1
            key = asset["key"]

            if key.startswith(SEED_PREFIX):
                seed_skipped += 1
                continue
            if key in referenced:
                referenced_skipped += 1
                continue

            created = asset["last_modified"]
            # Too new (maybe mid-form) or too old (outside the recent window) → leave it.
            if created is None or created > now - min_age or created < now - max_age:
                window_skipped += 1
                continue

            orphans.append((key, created))

        self._report_scan(scanned, seed_skipped, referenced_skipped, window_skipped, orphans)

        if not orphans:
            self.stdout.write(self.style.SUCCESS("No orphans to remove."))
            return

        if not commit:
            self.stdout.write(
                self.style.WARNING(
                    f"DRY-RUN: {len(orphans)} orphan(s) would be deleted. "
                    "Re-run with --commit to delete."
                )
            )
            return

        deleted = self._delete([key for key, _ in orphans])
        self.stdout.write(self.style.SUCCESS(f"Deleted {deleted} orphan image(s)."))

    def _referenced_keys(self):
        """Every storage key referenced by any DB record."""
        referenced = set()
        for thumbnail, gallery in Thing.objects.values_list("thumbnail", "gallery"):
            if thumbnail:
                referenced.add(thumbnail)
            for key in gallery or []:
                if key:
                    referenced.add(key)
        referenced.update(p for p in User.objects.values_list("photo", flat=True) if p)
        for thumbnail, welcome_doc in Collection.objects.values_list("thumbnail", "welcome_doc"):
            # welcome_doc is a PDF, and it lives in the same tree as the photos,
            # so this sweep sees it — it has to be protected like any other asset.
            if thumbnail:
                referenced.add(thumbnail)
            if welcome_doc:
                referenced.add(welcome_doc)
        return referenced

    def _iter_objects(self, prefix):
        """Yield every stored object under ``prefix``, paginated.

        Wrapped so a misconfigured or unreachable bucket surfaces as a clean
        CommandError rather than a traceback — this is run by hand, usually on a
        dyno, and the first thing to get wrong is the credentials.
        """
        try:
            yield from storage.iter_objects(prefix)
        except Exception as exc:  # noqa: BLE001 — surface any storage/config error cleanly
            raise CommandError(f"Could not list stored objects: {exc}") from exc

    def _delete(self, keys):
        """Delete in batches. Returns the count actually handed over.

        The batch size is well inside S3's own limit of 1000 per DeleteObjects
        call; it is kept at 100 so one failed batch costs a hundred orphans and
        not a thousand.
        """
        deleted = 0
        for i in range(0, len(keys), DELETE_BATCH):
            batch = keys[i : i + DELETE_BATCH]
            try:
                deleted += storage.delete_many(batch)
            except Exception as exc:  # noqa: BLE001
                self.stderr.write(self.style.ERROR(f"Failed to delete batch: {exc}"))
        return deleted

    def _report_scan(self, scanned, seed_skipped, referenced_skipped, window_skipped, orphans):
        self.stdout.write(
            f"Scanned {scanned} asset(s): "
            f"{referenced_skipped} in use, {seed_skipped} seed, "
            f"{window_skipped} outside the age window, {len(orphans)} orphan(s)."
        )
        for key, created in orphans:
            self.stdout.write(f"  orphan: {key}  (uploaded {created:%Y-%m-%d %H:%M} UTC)")

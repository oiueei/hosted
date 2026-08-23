"""
One-off: copy the demo's fixture images from Cloudinary into object storage.

**Temporary.** It exists for the length of the Cloudinary migration and is meant
to be deleted once production has been green for a week. It is a management
command rather than a loose script only because the set of images it copies is
derived from the seed data, which is Django code.

**Why only the seed folder.** The demo's images are a *static shared pool*: the
seed stores bare ids and prefixes them with ``oiueei/seed/`` at seed time, so
they are the same objects in every environment, referenced by every database
that has ever run ``seed_demo``. That is what makes this copy environment-free —
it runs once, from anywhere, against each bucket, and needs no production
database and no ``heroku run``. Real user uploads are **not** copied: that was a
deliberate scope decision, and the consequence, accepted knowingly, is that rows
still pointing at Cloudinary will 404 behind an ``<img>`` once reads move.

**Only the referenced images.** ``oiueei/seed/`` holds more files than the seed
uses — leftovers from earlier versions of the demo. They are not copied, and the
reason is specific: ``cleanup_orphan_images`` never touches ``oiueei/seed/`` (the
pool is shared, so an unreferenced file there is not evidence of an orphan). A
dead file copied into that folder is therefore permanent and invisible to every
sweep that will ever run.

Dry-run by default, like every other destructive-ish command here:

    python manage.py copy_seed_images                                  # dry-run
    python manage.py copy_seed_images --commit                         # dev bucket
    python manage.py copy_seed_images --bucket oiueei --commit         # production

Idempotent: an object already in the bucket is skipped, so a half-finished run
is just run again.
"""

import time

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core.management.commands.seed_demo import SEED_IMAGE_FOLDER
from core.models import Collection, Thing, User
from core.services import storage

# Cloudinary's delivery URL with no transformation and no format suffix returns
# the original bytes, and its Content-Type header is what the object should be
# stored as — more reliable than inferring one from the id, which carries no
# extension.
CLOUDINARY_DELIVERY = "https://res.cloudinary.com/{cloud}/image/upload/{key}"

# botocore does not retry a 404, and a freshly created bucket has been observed
# answering NoSuchBucket part-way through a tight loop. Whatever the cause, a
# copy that aborts halfway with a misleading error is worth four seconds of
# defence.
RETRY_WAITS = (0.5, 1, 2, 4)


class Command(BaseCommand):
    help = "Copy the demo's fixture images from Cloudinary into object storage (temporary)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--commit",
            action="store_true",
            help="Actually copy. Without this the command is a dry-run (default).",
        )
        parser.add_argument(
            "--bucket",
            help="Bucket to copy into. Defaults to OBJECT_STORAGE_BUCKET.",
        )

    def handle(self, *args, **options):
        commit = options["commit"]
        if options["bucket"]:
            # The storage module reads its bucket from settings and caches a
            # client per credential set, so pointing it elsewhere for one run
            # means saying so here. Confined to this temporary command on
            # purpose — nothing in the app switches buckets at runtime.
            settings.OBJECT_STORAGE_BUCKET = options["bucket"]
            storage._clients.clear()

        cloud = settings.CLOUDINARY_CLOUD_NAME
        if not cloud:
            raise CommandError("CLOUDINARY_URL is not configured — nothing to copy from.")

        bucket = settings.OBJECT_STORAGE_BUCKET
        keys = self._referenced_seed_keys()
        self.stdout.write(f"{len(keys)} referenced seed image(s) → bucket {bucket!r}")

        copied = skipped = 0
        failed = []

        for key in keys:
            try:
                if storage.exists(key):
                    skipped += 1
                    continue
                if not commit:
                    self.stdout.write(f"  would copy: {key}")
                    copied += 1
                    continue
                body, content_type = self._fetch(cloud, key)
                self._put_with_retry(key, body, content_type)
                self.stdout.write(f"  copied: {key}  ({content_type}, {len(body)} bytes)")
                copied += 1
            except Exception as exc:  # noqa: BLE001 — one bad file must not end the run
                failed.append((key, exc))
                self.stderr.write(self.style.ERROR(f"  FAILED {key}: {exc}"))

        self._report(commit, copied, skipped, failed)

    def _referenced_seed_keys(self):
        """Every ``oiueei/seed/`` key a seeded database actually points at.

        Read from the database rather than from the seed modules: the database is
        what the app resolves URLs against, and walking the seed dictionaries is
        a guess about their shape. Requires a seeded database — which is true of
        any developer machine and is why this never needs to run in production.
        """
        keys = set()
        for thumbnail, gallery in Thing.objects.values_list("thumbnail", "gallery"):
            if thumbnail:
                keys.add(thumbnail)
            keys.update(k for k in (gallery or []) if k)
        keys.update(p for p in User.objects.values_list("photo", flat=True) if p)
        for thumbnail, welcome_doc in Collection.objects.values_list("thumbnail", "welcome_doc"):
            if thumbnail:
                keys.add(thumbnail)
            if welcome_doc:
                keys.add(welcome_doc)

        seed = sorted(k for k in keys if k.startswith(SEED_IMAGE_FOLDER))
        if not seed:
            raise CommandError(
                f"No {SEED_IMAGE_FOLDER} keys in this database. Run `seed_demo` first — "
                "this command copies what the demo references, and an unseeded database "
                "references nothing."
            )
        return seed

    @staticmethod
    def _fetch(cloud, key):
        res = requests.get(CLOUDINARY_DELIVERY.format(cloud=cloud, key=key), timeout=60)
        res.raise_for_status()
        content_type = res.headers.get("Content-Type", "")
        if not content_type.startswith("image/"):
            # Storing whatever arrived would put the wrong type on a public
            # object, and the wrong type is exactly the bug this migration spent
            # a day finding.
            raise CommandError(f"unexpected Content-Type {content_type!r}")
        return res.content, content_type

    def _put_with_retry(self, key, body, content_type):
        for attempt, wait in enumerate((0, *RETRY_WAITS)):
            if wait:
                time.sleep(wait)
            try:
                storage.put(key, body, content_type)
                if attempt:
                    self.stdout.write(f"    (succeeded on retry {attempt})")
                return
            except Exception:  # noqa: BLE001
                if attempt == len(RETRY_WAITS):
                    raise

    def _report(self, commit, copied, skipped, failed):
        self.stdout.write(f"\n{copied} copied, {skipped} already present, {len(failed)} failed.")
        if failed:
            raise CommandError(f"{len(failed)} image(s) did not copy — see above.")
        if not commit:
            self.stdout.write(
                self.style.WARNING("DRY-RUN: nothing was written. Re-run with --commit.")
            )
        else:
            self.stdout.write(self.style.SUCCESS("Done."))

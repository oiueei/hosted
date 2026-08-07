"""Turn the digest on for accounts that predate its per-group off switch.

0126 changed ``User.notify_news``'s default to True which — as Django intends —
rewrites no existing row. Every account created before this release therefore
stays opted out, and the digest goes on reaching nobody: exactly the state the
design round set out to fix.

**This is the deliberate part of that change: it flips a preference a real
person already holds.** It is defensible only next to ``Collection.digest_muted``
(0125): a member who doesn't want one group's digest silences that group from
the footer of the first one they receive, and keeps every other email. Without
that control this migration would be a pre-ticked opt-in and should not exist.

Deleting this file is a valid, more conservative choice — existing accounts then
stay opted out and only new ones are subscribed.

**Complete in one pass, not re-runnable.** One pass leaves no ``notify_news=False``
row behind, so an immediate second pass matches nothing — but the filter selects
on the *current* value, not on a marker of who was migrated. Against a database
where somebody has opted out since, a re-run would sweep them straight back up
and silently overturn a choice they made deliberately.

What prevents that is Django's own bookkeeping — an applied migration does not
run again — **not** anything in this file. So: never ``--fake`` this one backwards
and re-apply it, and don't copy the pattern into a migration meant to be re-run.
Making it genuinely re-runnable would need a marker of who was already subscribed,
which is not worth a column for a one-shot backfill.

**Not automatically reversible.** A backward pass could only set everyone to
False, which would also opt out the people who had chosen True themselves — it
would destroy a preference rather than restore one. Reversing is a no-op, so a
rollback to 0126 leaves the flags where they are.
"""

from django.db import migrations


def subscribe_existing(apps, schema_editor):
    User = apps.get_model("core", "User")
    User.objects.filter(notify_news=False).update(notify_news=True)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0126_alter_user_notify_news"),
    ]

    operations = [
        migrations.RunPython(subscribe_existing, migrations.RunPython.noop),
    ]

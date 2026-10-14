from django.db import migrations, models

KIND_THING_TYPES = {
    "STALL": ("GIFT_THING", "SELL_THING"),
    "LIBRARY": ("LEND_THING", "RENT_THING"),
    "SHED": ("RESERVE_THING",),
}
FREE_VERB = {"STALL": "GIFT_THING", "LIBRARY": "LEND_THING"}


def _kind_of(verb):
    for kind, verbs in KIND_THING_TYPES.items():
        if verb in verbs:
            return kind
    return None


def assign_kinds(apps, schema_editor):
    """Give every collection the kind its verbs say, and tidy its verb list.

    The families a collection has are those of its ``allowed_thing_types`` and of
    its things' types. One family → that kind; none (empty list, no things) →
    STALL; several (only a stall and a library can mix: a reservation never could)
    → the family with most things, the first in kind order on a tie. The things of
    the other family stay as they are, with their verb. Returns how many were mixed.
    """
    Collection = apps.get_model("core", "Collection")
    order = list(KIND_THING_TYPES)
    mixed = 0
    for collection in Collection.objects.all():
        counts = dict.fromkeys(order, 0)
        for verb in collection.things.values_list("type", flat=True):
            kind = _kind_of(verb)
            if kind:
                counts[kind] += 1
        listed = {_kind_of(v) for v in collection.allowed_thing_types or []}
        families = [k for k in order if counts[k] or k in listed]
        if not families:
            kind = "STALL"
        elif len(families) == 1:
            kind = families[0]
        else:
            mixed += 1
            kind = max(families, key=lambda k: (counts[k], -order.index(k)))

        verbs = list(KIND_THING_TYPES[kind])
        if kind != "SHED" and collection.mode == "COMMUNITY":
            kept = [v for v in collection.allowed_thing_types or [] if v in verbs]
            if kept == [FREE_VERB[kind]]:
                verbs = kept
        collection.kind = kind
        collection.allowed_thing_types = verbs
        collection.save(update_fields=["kind", "allowed_thing_types"])
    if mixed:
        print(f"\n  {mixed} collection(s) held both families; kept the one with most things.")
    return mixed


class Migration(migrations.Migration):
    """Add ``Collection.kind`` and fill it from what each collection already holds.

    Going back drops the column and leaves the verb lists as they were rewritten:
    the kind was derived from the verbs, so nothing else needs undoing."""

    dependencies = [
        ("core", "0156_booking_return_reminded_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="collection",
            name="kind",
            field=models.CharField(
                choices=[("STALL", "Stall"), ("LIBRARY", "Library"), ("SHED", "Shed")],
                default="STALL",
                max_length=8,
            ),
        ),
        migrations.RunPython(assign_kinds, migrations.RunPython.noop),
    ]

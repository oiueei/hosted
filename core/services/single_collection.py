"""A thing lives in exactly one collection.

The app never puts a thing in a second one (the form, the CSV and the ZIP import
all create it in the collection it is for), and neither does the seed. The model
let it happen anyway, through ``Collection.things.add`` from either side, and
everything that reasons about "the" collection of a thing (its owner's team, who
may ask for it, what happens to it when a collection is deleted) was written for
one. A receiver on the M2M refuses the second membership before it is written,
from whichever side it is added.

Adding a thing to the collection it is already in is not an addition (Django
sends no ids for it), so it stays harmless. Rows written around the M2M manager,
straight into the through table, are not seen: nothing in the product does that.
"""

from django.core.exceptions import ValidationError
from django.db.models.signals import m2m_changed
from django.dispatch import receiver

from core.models import Collection

Membership = Collection.things.through


@receiver(m2m_changed, sender=Membership, dispatch_uid="single_collection.guard")
def _refuse_a_second_collection(sender, instance, action, reverse, pk_set, **kwargs):
    if action != "pre_add" or not pk_set:
        return
    if reverse:
        # `thing.collections.add(...)`: the ids are collections.
        in_another = Membership.objects.filter(thing_id=instance.pk).exists()
        in_several = len(pk_set) > 1
    else:
        # `collection.things.add(...)`: the ids are things not yet in this one.
        in_another = Membership.objects.filter(thing_id__in=pk_set).exists()
        in_several = False
    if in_another or in_several:
        raise ValidationError("A thing lives in exactly one collection.")

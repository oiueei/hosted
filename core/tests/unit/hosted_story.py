"""Fabricated-event helpers shared by the tests of `hosted/` that tell a story.

Each helper writes one event (and, unless told ``row=False``, the row it is about),
with an explicit ``created`` so a test reads as who did what on which day. Used by
`test_hosted_metrics.py` and `test_hosted_stats_summary.py`; not collected as tests.
"""

from datetime import datetime

from core.models import Collection, Event, Thing, User
from hosted.metrics import WEEK_TZ

K = Event.Kind

LALA = "La1aN1"  # a seed character: the operator signs in as them to try things


def madrid(day, hour=12, minute=0):
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=WEEK_TZ)


def log(kind, who="", on=None, collection="", thing="", type="", source=""):
    return Event.objects.create(
        kind=kind,
        actor_code=who,
        collection_code=collection,
        thing_code=thing,
        thing_type=type,
        source=source,
        created=on,
    )


def person(code):
    """The account behind a code the story mentions (a person who left has none)."""
    return User.objects.get_or_create(
        code=code, defaults={"email": f"{code.lower()}@your-domain.test", "name": code}
    )[0]


def creates(who, collection, on, row=True):
    """A collection created; ``row=False`` leaves nothing of it in the database."""
    if row:
        Collection.objects.get_or_create(
            code=collection, defaults={"owner": person(who), "headline": collection}
        )
    return log(K.COLLECTION_CREATED, who, on, collection=collection)


def joins(who, collection, on, source=Event.Source.INVITE, row=True):
    if row:
        person(who)
    return log(K.MEMBER_JOINED, who, on, collection=collection, source=source)


def adds(who, thing, collection, on, type="GIFT_THING", row=True):
    """A thing added; ``row=False`` leaves nothing of it in the database."""
    if row:
        Thing.objects.get_or_create(
            code=thing, defaults={"owner": person(who), "headline": thing, "type": type}
        )
    return log(K.THING_ADDED, who, on, collection=collection, thing=thing, type=type)


def asks(who, thing, on, type="GIFT_THING"):
    return log(K.HOLD_REQUESTED, who, on, thing=thing, type=type)

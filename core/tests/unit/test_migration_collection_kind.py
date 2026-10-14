"""0157 — every collection gets the kind its verbs say, and a tidy verb list.

Same scope as the other data-migration tests here: the RunPython function runs
against the live registry (the repo has no historical-state harness), so what is
pinned is the rule: which kind each shape of collection gets and what its
``allowed_thing_types`` becomes.
"""

import importlib

import pytest
from django.apps import apps as live_apps

from core.models import Collection, Thing, User

MIGRATION = importlib.import_module("core.migrations.0157_collection_kind")

GIFT, SELL = "GIFT_THING", "SELL_THING"
LEND, RENT = "LEND_THING", "RENT_THING"
RESERVE = "RESERVE_THING"


@pytest.fixture
def owner(db):
    return User.objects.create(code="MIGOW1", email="lolo21@your-domain.test", name="Owner")


def _collection(owner, code, verbs, things=(), mode="PROPRIETARY"):
    collection = Collection.objects.create(
        code=code, owner=owner, headline=code, allowed_thing_types=verbs, mode=mode
    )
    for n, verb in enumerate(things):
        thing = Thing.objects.create(
            code=f"{code[:3]}T{n:02d}", owner=owner, headline="x", type=verb
        )
        collection.things.add(thing)
    return collection


def _run():
    return MIGRATION.assign_kinds(live_apps, None)


def _after(collection):
    collection.refresh_from_db()
    return collection.kind, collection.allowed_thing_types


class TestTheKindFollowsTheVerbs:
    def test_a_pure_stall_stays_a_stall(self, owner):
        c = _collection(owner, "STALL1", [GIFT, SELL], [GIFT, SELL])
        _run()
        assert _after(c) == ("STALL", [GIFT, SELL])

    def test_a_library_with_an_empty_list_is_read_from_its_things(self, owner):
        c = _collection(owner, "LIBR01", [], [LEND, LEND])
        _run()
        assert _after(c) == ("LIBRARY", [LEND, RENT])

    def test_an_empty_collection_without_things_is_a_stall(self, owner):
        c = _collection(owner, "EMPT01", [])
        _run()
        assert _after(c) == ("STALL", [GIFT, SELL])

    def test_a_reservation_collection_is_a_shed(self, owner):
        c = _collection(owner, "SHED01", [RESERVE], [RESERVE])
        _run()
        assert _after(c) == ("SHED", [RESERVE])

    def test_a_mixed_one_takes_the_family_with_most_things_and_keeps_the_rest(self, owner):
        c = _collection(owner, "MIXD01", [GIFT, LEND], [GIFT, GIFT, LEND])

        assert _run() == 1

        assert _after(c) == ("STALL", [GIFT, SELL])
        assert c.things.filter(type=LEND).count() == 1

    def test_a_tie_goes_to_the_first_kind(self, owner):
        c = _collection(owner, "TIE001", [LEND, GIFT], [LEND, GIFT])
        _run()
        assert _after(c)[0] == "STALL"

    def test_a_count_is_returned_only_for_mixed_ones(self, owner):
        _collection(owner, "ONE001", [GIFT], [GIFT])
        assert _run() == 0


class TestTheVerbListIsNormalised:
    def test_a_community_that_took_only_the_free_verb_keeps_it(self, owner):
        c = _collection(owner, "COMF01", [GIFT], mode="COMMUNITY")
        _run()
        assert _after(c) == ("STALL", [GIFT])

    def test_a_community_library_that_lent_only_keeps_it(self, owner):
        c = _collection(owner, "COML01", [LEND], mode="COMMUNITY")
        _run()
        assert _after(c) == ("LIBRARY", [LEND])

    def test_a_community_that_took_only_the_paid_verb_gets_both(self, owner):
        c = _collection(owner, "COMP01", [SELL], mode="COMMUNITY")
        _run()
        assert _after(c) == ("STALL", [GIFT, SELL])

    def test_a_proprietary_collection_always_gets_both(self, owner):
        c = _collection(owner, "PROP01", [SELL])
        _run()
        assert _after(c) == ("STALL", [GIFT, SELL])


class TestTheModelSide:
    @pytest.mark.parametrize(
        "kind,code,path",
        [
            ("STALL", "AAA111", "/stall/AAA111"),
            ("LIBRARY", "BBB222", "/library/BBB222"),
            ("SHED", "CCC333", "/shed/CCC333"),
        ],
    )
    def test_path_is_the_kinds_address(self, owner, kind, code, path):
        assert Collection(code=code, kind=kind).path() == path

    def test_only_a_shed_is_a_reservations_collection(self):
        assert Collection(kind="SHED").is_reservations_collection()
        assert not Collection(
            kind="STALL", allowed_thing_types=[RESERVE]
        ).is_reservations_collection()
        assert not Collection(kind="LIBRARY").is_reservations_collection()

    @pytest.mark.parametrize(
        "verb,kind",
        [
            (GIFT, "STALL"),
            (SELL, "STALL"),
            (LEND, "LIBRARY"),
            (RENT, "LIBRARY"),
            (RESERVE, "SHED"),
            ("WISH_THING", None),
        ],
    )
    def test_a_verb_belongs_to_one_kind(self, verb, kind):
        from core.models.collection import kind_for_thing_type

        assert kind_for_thing_type(verb) == kind


@pytest.mark.django_db
class TestTheFactoryFollowsTheVerbs:
    @pytest.mark.parametrize(
        "verbs,kind",
        [([RESERVE], "SHED"), ([LEND, RENT], "LIBRARY"), ([GIFT], "STALL"), ([], "STALL")],
    )
    def test_a_collection_built_with_verbs_gets_their_kind(self, verbs, kind):
        from core.tests.factories import CollectionFactory

        assert CollectionFactory(allowed_thing_types=verbs).kind == kind

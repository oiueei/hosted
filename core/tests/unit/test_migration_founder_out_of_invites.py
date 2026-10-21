"""0163 — a founder found in their own group's ``invites`` leaves it, and only that.

Same scope as the other data-migration tests here: the RunPython function runs
against the live registry, so what is pinned is the rule — who leaves which set,
and who stays — not the migration executor.
"""

import importlib

import pytest
from django.apps import apps as live_apps

from core.models import Collection, Thing, User

MIGRATION = importlib.import_module("core.migrations.0163_founder_out_of_invites")


def _run():
    return MIGRATION.forget_founders_membership(live_apps, None)


@pytest.fixture
def people(db):
    return {
        code: User.objects.create(code=code, email=f"{code.lower()}@your-domain.test", name=code)
        for code in ("FOUN01", "CURA01", "MEMB01")
    }


@pytest.fixture
def group(people):
    return Collection.objects.create(code="GRP001", owner=people["FOUN01"], headline="Street")


def test_a_founder_in_invites_and_co_owners_leaves_both(group, people):
    group.invites.add(people["FOUN01"])
    group.co_owners.add(people["FOUN01"])

    _run()

    assert not group.invites.filter(code="FOUN01").exists()
    assert not group.co_owners.filter(code="FOUN01").exists()


def test_a_founder_only_in_co_owners_leaves_it(group, people):
    group.co_owners.add(people["FOUN01"])

    _run()

    assert not group.co_owners.filter(code="FOUN01").exists()


def test_other_members_and_co_curators_of_that_group_stay(group, people):
    group.invites.add(people["FOUN01"], people["CURA01"], people["MEMB01"])
    group.co_owners.add(people["FOUN01"], people["CURA01"])

    _run()

    assert set(group.invites.values_list("code", flat=True)) == {"CURA01", "MEMB01"}
    assert set(group.co_owners.values_list("code", flat=True)) == {"CURA01"}


def test_the_founders_things_are_not_touched(group, people):
    group.invites.add(people["FOUN01"])
    thing = Thing.objects.create(
        code="THNG01", owner=people["FOUN01"], headline="x", type="GIFT_THING"
    )
    group.things.add(thing)

    _run()

    assert Thing.objects.filter(code="THNG01").exists()
    assert group.things.filter(code="THNG01").exists()


def test_a_member_of_one_group_who_founds_another_keeps_the_first_membership(group, people):
    other = Collection.objects.create(code="GRP002", owner=people["MEMB01"], headline="Block")
    group.invites.add(people["MEMB01"])
    other.invites.add(people["MEMB01"])

    _run()

    assert group.invites.filter(code="MEMB01").exists()
    assert not other.invites.filter(code="MEMB01").exists()


def test_running_it_twice_changes_nothing_more(group, people):
    group.invites.add(people["FOUN01"], people["MEMB01"])

    _run()
    _run()

    assert set(group.invites.values_list("code", flat=True)) == {"MEMB01"}

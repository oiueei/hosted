"""A deletion is recorded in the Event log when the row goes, whichever way it goes.

Fixtures build objects through the ORM, so the ``events`` table starts empty and exact
counts can be asserted. Addresses avoid the ones ``conftest.py`` already holds
(``lala3@`` and ``lolo2@``): a collision in a test that only runs on Postgres is seen
by nobody until the CI.
"""

from io import StringIO

import pytest
from django.core.management import call_command
from django.db import transaction

from core.models import Collection, Event, Thing, User
from core.services.account_service import delete_account
from core.services.deletion_events import deleting_as, deletion_events_suppressed
from core.tests.factories import also_in

KINDS = [Event.Kind.COLLECTION_DELETED, Event.Kind.THING_REMOVED, Event.Kind.MEMBER_LEFT]


def deletion_events():
    return Event.objects.filter(kind__in=KINDS)


def make_user(code, email):
    return User.objects.create(code=code, email=email)


def make_thing(code, owner, *collections, type="GIFT_THING"):
    thing = Thing.objects.create(code=code, owner=owner, headline=code, type=type)
    for collection in collections:
        collection.things.add(thing)
    return thing


@pytest.mark.django_db
class TestDeletingThroughTheApi:
    def test_deleting_a_collection_logs_it_and_each_orphaned_thing(
        self, authenticated_client, user
    ):
        doomed = Collection.objects.create(code="EVDEL1", owner=user, headline="Doomed")
        make_thing("EVORP1", user, doomed, type="LEND_THING")
        make_thing("EVORP2", user, doomed)
        kept = Collection.objects.create(code="EVKEP1", owner=user, headline="Kept")
        shared = make_thing("EVSHR1", user, doomed)
        # The product keeps a thing in one collection; this case is built around the
        # guard to pin what the delete does if it ever meets one.
        also_in(kept, shared)

        response = authenticated_client.delete("/api/v1/collections/EVDEL1/")

        assert response.status_code == 204
        deleted = Event.objects.get(kind=Event.Kind.COLLECTION_DELETED)
        assert (deleted.actor_code, deleted.collection_code) == (user.code, "EVDEL1")
        removed = Event.objects.filter(kind=Event.Kind.THING_REMOVED)
        # The thing that still lives in another collection is not removed, nor deleted.
        assert Thing.objects.filter(code="EVSHR1").exists()
        assert {(e.thing_code, e.thing_type, e.actor_code) for e in removed} == {
            ("EVORP1", "LEND_THING", user.code),
            ("EVORP2", "GIFT_THING", user.code),
        }
        assert deletion_events().count() == 3

    def test_deleting_a_thing_logs_exactly_one_event(self, authenticated_client, user, thing):
        response = authenticated_client.delete(f"/api/v1/things/{thing.code}/")

        assert response.status_code == 204
        event = deletion_events().get()
        assert event.kind == Event.Kind.THING_REMOVED
        assert (event.actor_code, event.thing_code) == (user.code, thing.code)


@pytest.mark.django_db
class TestDeletingAnyOtherWay:
    def test_a_direct_delete_logs_with_no_actor(self, user):
        collection = Collection.objects.create(code="EVADM1", owner=user, headline="Admin")
        thing = make_thing("EVADM2", user, collection)

        thing.delete()
        collection.delete()

        assert {(e.kind, e.actor_code) for e in deletion_events()} == {
            (Event.Kind.THING_REMOVED, ""),
            (Event.Kind.COLLECTION_DELETED, ""),
        }

    def test_the_code_survives_in_the_event_after_the_pk_is_nulled(self, user):
        collection = Collection.objects.create(code="EVPKS1", owner=user, headline="Pk")

        collection.delete()

        assert collection.pk is None
        assert deletion_events().get().collection_code == "EVPKS1"

    def test_a_queryset_delete_logs_every_row(self, user):
        for code in ("EVQS01", "EVQS02", "EVQS03"):
            make_thing(code, user)

        Thing.objects.filter(owner=user).delete()

        assert sorted(e.thing_code for e in deletion_events()) == ["EVQS01", "EVQS02", "EVQS03"]

    def test_a_rolled_back_delete_leaves_no_event(self, user):
        collection = Collection.objects.create(code="EVRB01", owner=user, headline="Rollback")

        with pytest.raises(RuntimeError), transaction.atomic():
            collection.delete()
            raise RuntimeError("undo")

        assert Collection.objects.filter(code="EVRB01").exists()
        assert not deletion_events().exists()

    def test_deleting_as_attributes_and_does_not_leak(self, user):
        first = make_thing("EVAS01", user)
        second = make_thing("EVAS02", user)

        with deleting_as(user):
            first.delete()
        second.delete()

        actors = {e.thing_code: e.actor_code for e in deletion_events()}
        assert actors == {"EVAS01": user.code, "EVAS02": ""}

    def test_suppressed_block_logs_nothing_and_restores_recording(self, user):
        first = make_thing("EVSUP1", user)
        second = make_thing("EVSUP2", user)

        with deletion_events_suppressed():
            first.delete()
        assert not deletion_events().exists()

        second.delete()
        assert deletion_events().get().thing_code == "EVSUP2"


@pytest.mark.django_db
class TestDeletingAnAccount:
    def test_erasure_logs_their_collections_things_and_memberships(self):
        leaver = make_user("EVLEV1", "lele6@your-domain.test")
        host = make_user("EVHST1", "lili6@your-domain.test")
        mine = Collection.objects.create(code="EVMIN1", owner=leaver, headline="Mine")
        theirs = Collection.objects.create(code="EVTHR1", owner=host, headline="Theirs")
        theirs.invites.add(leaver)
        make_thing("EVMYT1", leaver, mine)
        make_thing("EVHST2", host, theirs)

        delete_account(leaver)

        got = {(e.kind, e.actor_code, e.collection_code, e.thing_code) for e in deletion_events()}
        assert got == {
            (Event.Kind.COLLECTION_DELETED, "EVLEV1", "EVMIN1", ""),
            (Event.Kind.THING_REMOVED, "EVLEV1", "", "EVMYT1"),
            (Event.Kind.MEMBER_LEFT, "EVLEV1", "EVTHR1", ""),
        }

    def test_the_retention_purge_logs_the_memberships_it_ends(self):
        member = make_user("EVPRG1", "lulu6@your-domain.test")
        host = make_user("EVPRG2", "lili7@your-domain.test")
        group = Collection.objects.create(code="EVPRG3", owner=host, headline="Group")
        group.invites.add(member)

        # The bulk delete the purge uses for its own steps.
        User.objects.filter(code=member.code).delete()

        event = deletion_events().get()
        assert (event.kind, event.actor_code, event.collection_code) == (
            Event.Kind.MEMBER_LEFT,
            "EVPRG1",
            "EVPRG3",
        )


@pytest.mark.django_db
class TestSeedReset:
    def test_reset_writes_no_deletion_event(self):
        call_command("seed_demo", stdout=StringIO())
        assert Thing.objects.exists()

        call_command("seed_demo", "--reset", stdout=StringIO())

        assert not deletion_events().exists()

"""The message to everyone is signed by the entity the dinamizador answers for."""

import pytest
from django.core import mail
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from core.models import Collection, NetworkPoint, User
from core.models.notification import InAppNotification
from core.tests.factories import CollectionFactory

LEND, RENT = "LEND_THING", "RENT_THING"


def client_for(user):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    return client


def _user(code, name):
    return User.objects.create(code=code, email=f"{name.lower()}@your-domain.test", name=name)


def broadcast(group, sender):
    mail.outbox.clear()
    return client_for(sender).post(
        f"/api/v1/collections/{group.code}/broadcast/",
        {"message": "Open on Saturday"},
        format="json",
    )


@pytest.fixture
def world(db):
    founder, lele, lolo = _user("FOUN01", "Lala"), _user("ENTA01", "Lele"), _user("MEMB01", "Lolo")
    network = CollectionFactory(
        owner=founder, mode=Collection.Mode.NETWORK, allowed_thing_types=[LEND, RENT]
    )
    network.invites.add(lele, lolo)
    network.co_owners.add(lele)
    return {"network": network, "founder": founder, "lele": lele, "lolo": lolo}


def test_with_a_point_the_message_is_signed_by_its_entity(world):
    NetworkPoint.objects.create(
        collection=world["network"], user=world["lele"], entity_name="Cooperativa La Fusteria"
    )

    res = broadcast(world["network"], world["lele"])

    assert res.status_code == status.HTTP_200_OK
    [message] = [m for m in mail.outbox if m.to == ["lolo@your-domain.test"]]
    assert "Cooperativa La Fusteria" in message.body
    assert "Lele" not in message.body
    notice = InAppNotification.objects.get(
        user=world["lolo"], type=InAppNotification.Type.BROADCAST
    )
    assert notice.payload["owner_name"] == "Cooperativa La Fusteria"


def test_without_a_point_it_is_signed_by_the_person(world):
    broadcast(world["network"], world["lele"])

    [message] = [m for m in mail.outbox if m.to == ["lolo@your-domain.test"]]
    assert "Lele" in message.body
    notice = InAppNotification.objects.get(
        user=world["lolo"], type=InAppNotification.Type.BROADCAST
    )
    assert notice.payload["owner_name"] == "Lele"


def test_a_point_without_an_entity_name_signs_with_the_persons_name(world):
    NetworkPoint.objects.create(collection=world["network"], user=world["lele"], address="Calle 1")

    broadcast(world["network"], world["lele"])

    notice = InAppNotification.objects.get(
        user=world["lolo"], type=InAppNotification.Type.BROADCAST
    )
    assert notice.payload["owner_name"] == "Lele"


def test_each_dinamizador_signs_with_their_own_point(world):
    NetworkPoint.objects.create(
        collection=world["network"], user=world["founder"], entity_name="Federación"
    )
    NetworkPoint.objects.create(
        collection=world["network"], user=world["lele"], entity_name="Cooperativa La Fusteria"
    )

    broadcast(world["network"], world["founder"])

    notice = InAppNotification.objects.get(
        user=world["lolo"], type=InAppNotification.Type.BROADCAST
    )
    assert notice.payload["owner_name"] == "Federación"


def test_outside_a_network_it_is_signed_by_the_person(db):
    founder, lolo = _user("FOUN01", "Lala"), _user("MEMB01", "Lolo")
    group = CollectionFactory(owner=founder, mode=Collection.Mode.PROPRIETARY)
    group.invites.add(lolo)
    NetworkPoint.objects.create(collection=group, user=founder, entity_name="Ghost entity")

    broadcast(group, founder)

    notice = InAppNotification.objects.get(user=lolo, type=InAppNotification.Type.BROADCAST)
    assert notice.payload["owner_name"] == "Lala"

"""In a network a notice about a thing reaches the entity that runs it, and nobody else.

Every fan-out to "the team that runs the thing" reads ``Thing.managers()``, which in a
network is the thing's owner alone. This pins it send by send, with a founder and two
entities: the one that owns the thing hears, the founder and the other entity do not.
"""

from datetime import timedelta

import pytest
from django.core import mail
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from core.models import FAQ, BookingPeriod, Collection, User
from core.models.notification import InAppNotification
from core.tests.factories import BookingPeriodFactory, CollectionFactory, ThingFactory

LEND, RENT = "LEND_THING", "RENT_THING"
FOUNDER, OWNER, OTHER, ASKER = (
    "lala@your-domain.test",
    "lele@your-domain.test",
    "lili@your-domain.test",
    "lolo@your-domain.test",
)


def client_for(user):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    return client


def _user(code, name):
    return User.objects.create(code=code, email=f"{name.lower()}@your-domain.test", name=name)


@pytest.fixture
def net(db):
    founder, lele, lili, lolo = (
        _user("FOUN01", "Lala"),
        _user("ENTA01", "Lele"),
        _user("ENTB01", "Lili"),
        _user("ASKR01", "Lolo"),
    )
    group = CollectionFactory(
        owner=founder, mode=Collection.Mode.NETWORK, allowed_thing_types=[LEND, RENT]
    )
    group.invites.add(lele, lili, lolo)
    group.co_owners.add(lele, lili)
    thing = ThingFactory(owner=lele, type=LEND, headline="Cordless drill")
    group.things.add(thing)
    return {"group": group, "thing": thing, "lele": lele, "lolo": lolo, "founder": founder}


def _recipients():
    return sorted(addr for m in mail.outbox for addr in m.to)


def _holders(kind):
    return sorted(InAppNotification.objects.filter(type=kind).values_list("user__email", flat=True))


def _request(net):
    today = timezone.localdate()
    return client_for(net["lolo"]).post(
        f"/api/v1/things/{net['thing'].code}/request/",
        {
            "start_date": str(today + timedelta(days=3)),
            "end_date": str(today + timedelta(days=6)),
            "collection_code": net["group"].code,
        },
        format="json",
    )


@pytest.mark.django_db
class TestRequests:
    def test_the_request_email_reaches_the_entity_that_owns_the_thing_only(self, net):
        mail.outbox.clear()

        res = _request(net)

        assert res.status_code == 201, res.data
        # The entity gets the request; the requester gets their confirmation.
        assert _recipients() == sorted([OWNER, ASKER])

    def test_the_request_notice_in_the_inbox_goes_to_the_owner_only(self, net):
        _request(net)

        assert _holders(InAppNotification.Type.BOOKING_REQUESTED) == [OWNER]

    def test_the_requester_is_told_one_person_was_informed(self, net):
        mail.outbox.clear()

        _request(net)

        confirmation = next(m for m in mail.outbox if m.to == [ASKER])
        assert "the person who runs it" in confirmation.body

    def test_the_owner_deciding_leaves_a_record_for_nobody(self, net):
        _request(net)
        booking = BookingPeriod.objects.get()

        client_for(net["lele"]).post(f"/api/v1/bookings/{booking.code}/accept/")

        assert _holders(InAppNotification.Type.BOOKING_DECIDED) == []
        assert _holders(InAppNotification.Type.BOOKING_ACCEPTED) == [ASKER]


@pytest.mark.django_db
class TestQuestions:
    def _ask(self, net):
        return client_for(net["lolo"]).post(
            f"/api/v1/things/{net['thing'].code}/faq/", {"question": "Batteries?"}, format="json"
        )

    def test_a_question_email_reaches_the_owner_only(self, net):
        mail.outbox.clear()

        res = self._ask(net)

        assert res.status_code == 201, res.data
        assert _recipients() == [OWNER]

    def test_a_question_notice_in_the_inbox_goes_to_the_owner_only(self, net):
        self._ask(net)

        assert _holders(InAppNotification.Type.FAQ_QUESTION) == [OWNER]

    def test_an_answer_reaches_the_asker_and_nobody_on_the_team(self, net):
        self._ask(net)
        faq = FAQ.objects.get()
        mail.outbox.clear()

        client_for(net["lele"]).post(
            f"/api/v1/faq/{faq.code}/answer/", {"answer": "Two."}, format="json"
        )

        assert _recipients() == [ASKER]

    def test_hiding_a_question_reaches_the_asker_and_nobody_on_the_team(self, net):
        self._ask(net)
        faq = FAQ.objects.get()
        mail.outbox.clear()

        client_for(net["lele"]).post(f"/api/v1/faq/{faq.code}/hide/")

        assert _recipients() == [ASKER]


@pytest.mark.django_db
class TestReminders:
    def _loan(self, net, *, start, end):
        return BookingPeriodFactory(
            thing_code=net["thing"],
            requester_code=net["lolo"],
            thing_type=LEND,
            status=BookingPeriod.Status.ACCEPTED,
            start_date=start,
            end_date=end,
        )

    def test_the_return_reminder_reaches_the_owner_and_the_borrower_only(self, net):
        today = timezone.localdate()
        self._loan(net, start=today - timedelta(days=5), end=today + timedelta(days=1))
        mail.outbox.clear()

        call_command("send_reminders")

        assert _recipients() == sorted([OWNER, ASKER])

    def test_the_pickup_reminder_reaches_the_owner_and_the_borrower_only(self, net):
        today = timezone.localdate()
        self._loan(net, start=today + timedelta(days=1), end=today + timedelta(days=5))
        mail.outbox.clear()

        call_command("send_reminders")

        assert _recipients() == sorted([OWNER, ASKER])


@pytest.mark.django_db
def test_a_report_reaches_the_owner_only(net):
    mail.outbox.clear()

    res = client_for(net["lolo"]).post(f"/api/v1/things/{net['thing'].code}/report/")

    assert res.status_code == 200
    assert _recipients() == [OWNER]
    assert _holders(InAppNotification.Type.THING_REPORTED) == [OWNER]

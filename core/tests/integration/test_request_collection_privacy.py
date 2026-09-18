"""Which collection a request is "made through" — only ever one the requester
may read.

A thing can sit in a PRIVATE group and a PUBLIC one at once (the owner adds it
to both). A member of the public one requests it; the request names a
collection (`collection_code`, whatever the client sent) or names none and the
server approximates. Whatever it resolves to decides the owner's note in the
requester's emails (`Collection.email_note`, written for that group's own
members) and whose rental rules apply. Before the 2026-09-18 security round
the private group could be that collection: named outright, or reached by the
fallbacks — first collection with rules, lowest code — which never asked
whether the requester could open it.
"""

from datetime import timedelta

import pytest
from django.core import mail
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from core.models import Collection, Thing
from core.models.booking import BookingPeriod

pytestmark = pytest.mark.django_db

PRIVATE_NOTE = "Family only: the key is under the blue pot."
PUBLIC_NOTE = "Pick-up at the community centre desk."


def _client(user):
    client = APIClient()
    token = RefreshToken.for_user(user).access_token
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


@pytest.fixture
def groups(user, user2):
    # The private group's code sorts first on purpose: `.first()` on the M2M
    # returns the lowest code, which is how the private one used to win.
    private = Collection.objects.create(
        code="AAPRIV",
        owner=user,
        headline="Family",
        visibility=Collection.Visibility.PRIVATE,
        email_note=PRIVATE_NOTE,
    )
    public = Collection.objects.create(
        code="ZZPUBL",
        owner=user,
        headline="Neighbourhood",
        visibility=Collection.Visibility.PUBLIC,
        email_note=PUBLIC_NOTE,
    )
    public.invites.add(user2)
    return {"private": private, "public": public}


def _thing(owner, groups, type_, code):
    thing = Thing.objects.create(code=code, type=type_, owner=owner, headline="Drill")
    groups["private"].things.add(thing)
    groups["public"].things.add(thing)
    return thing


def _requester_mail(user2):
    return [m for m in mail.outbox if m.to == [user2.email]]


class TestTheRequesterNeverGetsAPrivateGroupsNote:
    def test_naming_the_private_group_does_not_reach_its_note(self, user, user2, groups):
        thing = _thing(user, groups, Thing.Type.GIFT_THING, "GIFT01")
        mail.outbox.clear()

        response = _client(user2).post(
            f"/api/v1/things/{thing.code}/request/",
            {"collection_code": "AAPRIV"},
            format="json",
        )

        assert response.status_code == 201
        [confirmation] = _requester_mail(user2)
        assert PRIVATE_NOTE not in confirmation.body
        assert PRIVATE_NOTE not in confirmation.alternatives[0][0]
        # The group they can read stands in for the one they can't.
        assert PUBLIC_NOTE in confirmation.body

    def test_the_rules_fallback_skips_a_group_they_cannot_read(self, user, user2, groups):
        # With no collection named, the first collection defining rental rules
        # governs — and here that is the private one.
        groups["private"].rental_weekdays = list(range(7))
        groups["private"].save(update_fields=["rental_weekdays"])
        thing = _thing(user, groups, Thing.Type.LEND_THING, "LEND01")
        start = timezone.localdate() + timedelta(days=3)
        mail.outbox.clear()

        response = _client(user2).post(
            f"/api/v1/things/{thing.code}/request/",
            {"start_date": str(start), "end_date": str(start + timedelta(days=2))},
            format="json",
        )

        assert response.status_code == 201
        [confirmation] = _requester_mail(user2)
        assert PRIVATE_NOTE not in confirmation.body

    def test_the_acceptance_carries_the_readable_groups_note(self, user, user2, groups):
        thing = _thing(user, groups, Thing.Type.GIFT_THING, "GIFT02")
        booking = BookingPeriod.objects.create(
            thing_code=thing,
            thing_type=thing.type,
            requester_code=user2,
            requester_email=user2.email,
            owner_code=user,
        )
        mail.outbox.clear()

        response = _client(user).post(f"/api/v1/bookings/{booking.code}/accept/")

        assert response.status_code == 200
        [decision] = _requester_mail(user2)
        assert PRIVATE_NOTE not in decision.body
        assert PRIVATE_NOTE not in decision.alternatives[0][0]
        assert PUBLIC_NOTE in decision.body

    def test_a_member_of_both_still_gets_the_group_they_named(self, user, user2, groups):
        # The guard narrows to what the requester may read; it doesn't stop
        # the request's own context winning when they genuinely are inside.
        groups["private"].invites.add(user2)
        thing = _thing(user, groups, Thing.Type.GIFT_THING, "GIFT03")
        mail.outbox.clear()

        _client(user2).post(
            f"/api/v1/things/{thing.code}/request/",
            {"collection_code": "AAPRIV"},
            format="json",
        )

        [confirmation] = _requester_mail(user2)
        assert PRIVATE_NOTE in confirmation.body


class TestRentalRulesComeFromAGroupTheRequesterCanRead:
    def test_naming_a_rule_free_private_group_does_not_lift_the_rules(self, user, user2, groups):
        # The public group fixes a one-week loan; the private one has no rules.
        # Naming the private group used to pick it — and with it, no rules.
        groups["public"].rental_durations = [7]
        groups["public"].save(update_fields=["rental_durations"])
        thing = _thing(user, groups, Thing.Type.LEND_THING, "LEND02")
        start = timezone.localdate() + timedelta(days=3)

        response = _client(user2).post(
            f"/api/v1/things/{thing.code}/request/",
            {
                "start_date": str(start),
                "end_date": str(start + timedelta(days=2)),
                "collection_code": "AAPRIV",
            },
            format="json",
        )

        assert response.status_code == 400
        assert not BookingPeriod.objects.filter(thing_code=thing).exists()

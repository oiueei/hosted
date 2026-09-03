"""The open door of this deployment — the `hosted/` app's `/auth/pop-in/`.

**This file tests code that is not in the standalone repository.** It lives under
`core/tests/` for one practical reason: `pytest.ini` sets `testpaths = core/tests`
and is merged unchanged from upstream, so a suite anywhere else would simply
never run — which is exactly how an app's tests go missing in CI (it happened
once already, to another app). A file added here conflicts with nothing
upstream; editing `pytest.ini` in this repo would conflict on every sync,
forever.

What is worth protecting, and why each half matters:

**The door opens.** An email alone gets an account, membership of the demo
collections and a magic link. Upstream refuses precisely this — it is the whole
reason the app exists — so if it ever stopped working, the deployment would
quietly become invite-only and nobody would notice until the sign-ups stopped.

**The door does not weaken the product.** Someone arriving with a real
collection in hand must be handled by the product's own view, unchanged: same
membership, same `target_code`, same landing. The service layer wraps OIUEEI;
it must not fork it.
"""

import pytest
from django.core import mail

from core.models import RSVP, Collection, Event, User

POP_IN_URL = "/api/v1/auth/pop-in/"
JOIN_URL = "/api/v1/auth/join/"


@pytest.fixture
def onboarding(db, user):
    return Collection.objects.create(
        code="ONBHST", owner=user, headline="Lala's things", is_onboarding=True
    )


@pytest.mark.django_db
class TestTheOpenDoor:
    def test_an_email_alone_creates_an_account_and_joins_the_demo(self, api_client, onboarding):
        response = api_client.post(POP_IN_URL, {"email": "curious@test.com"}, format="json")

        assert response.status_code == 200
        visitor = User.objects.get(email="curious@test.com")
        assert onboarding.invites.filter(code=visitor.code).exists()
        assert len(mail.outbox) == 1

    def test_the_magic_link_carries_no_target_so_they_land_on_welcome(self, api_client, onboarding):
        """They came to look around, not to reach one group.

        An empty `target_code` plus `origin=POPIN` is what makes VerifyLinkView
        answer `landing: "welcome"` — the contract upstream keeps for exactly
        this app (see `core/views/auth.py`).
        """
        api_client.post(POP_IN_URL, {"email": "curious@test.com"}, format="json")

        rsvp = RSVP.objects.get(user_email="curious@test.com")
        assert rsvp.origin == RSVP.Origin.POPIN
        assert not rsvp.target_code

    def test_it_works_with_no_onboarding_collections_at_all(self, api_client):
        """A deployment that has not seeded yet still admits people.

        The account is real and the magic link works; there is simply nothing to
        put them in. Refusing here would make the door depend on demo data.
        """
        response = api_client.post(POP_IN_URL, {"email": "early@test.com"}, format="json")

        assert response.status_code == 200
        assert User.objects.filter(email="early@test.com").exists()
        assert len(mail.outbox) == 1

    def test_an_existing_account_is_not_duplicated(self, api_client, user, onboarding):
        response = api_client.post(POP_IN_URL, {"email": user.email}, format="json")

        assert response.status_code == 200
        assert User.objects.filter(email=user.email).count() == 1
        assert onboarding.invites.filter(code=user.code).exists()

    def test_a_returning_visitor_is_counted_once(self, api_client, onboarding):
        """Three visits, one member — the join side effects are the product's.

        This is why `_join_collection` is imported rather than reimplemented: it
        decides "first time" before the idempotent M2M add, so a repeat visit
        logs no second MEMBER_JOINED and re-sends no welcome document.
        """
        for _ in range(3):
            api_client.post(POP_IN_URL, {"email": "again@test.com"}, format="json")

        visitor = User.objects.get(email="again@test.com")
        assert (
            Event.objects.filter(kind=Event.Kind.MEMBER_JOINED, actor_code=visitor.code).count()
            == 1
        )

    def test_the_join_is_attributed_to_the_open_door(self, api_client, onboarding):
        """`source=ONBOARDING` is the only thing that tells this door apart later.

        Upstream has no producer for that value; this app is it. Without it the
        operator cannot answer "is the open door worth keeping?", which is the
        question it exists to be judged on.
        """
        api_client.post(POP_IN_URL, {"email": "counted@test.com"}, format="json")

        visitor = User.objects.get(email="counted@test.com")
        event = Event.objects.get(kind=Event.Kind.MEMBER_JOINED, actor_code=visitor.code)
        assert event.source == Event.Source.ONBOARDING

    def test_a_new_visitor_gets_their_first_email_in_their_own_language(
        self, api_client, onboarding
    ):
        api_client.post(POP_IN_URL, {"email": "nova@test.com", "language": "ca"}, format="json")

        assert User.objects.get(email="nova@test.com").language == "ca"
        assert "benvinguda" in mail.outbox[0].subject


@pytest.mark.django_db
class TestItDoesNotForkTheProduct:
    """A visitor pointed at a real collection is the product's business."""

    def test_a_public_collection_code_joins_that_collection_instead(
        self, api_client, public_collection, onboarding
    ):
        response = api_client.post(
            POP_IN_URL,
            {"email": "visitor@test.com", "collection_code": public_collection.code},
            format="json",
        )

        assert response.status_code == 200
        visitor = User.objects.get(email="visitor@test.com")
        assert public_collection.invites.filter(code=visitor.code).exists()
        # Not also dropped into the demo: they came somewhere specific.
        assert not onboarding.invites.filter(code=visitor.code).exists()

    def test_that_path_still_stamps_the_collection_for_the_landing(
        self, api_client, public_collection
    ):
        api_client.post(
            POP_IN_URL,
            {"email": "visitor@test.com", "collection_code": public_collection.code},
            format="json",
        )

        rsvp = RSVP.objects.get(user_email="visitor@test.com")
        assert rsvp.target_code == public_collection.code

    def test_a_private_code_is_not_a_way_in_here_either(self, api_client, collection, onboarding):
        """Delegating must not soften the product's own refusal.

        A PRIVATE collection's code is ignored — as upstream ignores it — and the
        visitor falls through to the open door, which is this deployment's answer
        to "someone typed something we don't recognise", not a way into that group.
        """
        response = api_client.post(
            POP_IN_URL,
            {"email": "prober@test.com", "collection_code": collection.code},
            format="json",
        )

        assert response.status_code == 200
        assert not collection.invites.filter(email="prober@test.com").exists()
        assert onboarding.invites.filter(email="prober@test.com").exists()


@pytest.mark.django_db
class TestTheTwoDoorsAnswerAlike:
    def test_pop_in_and_join_are_byte_for_byte_identical(self, api_client, public_collection):
        """Two views on one URL space must not be distinguishable from outside.

        The anti-enumeration guarantee upstream built into `/auth/join/` is worth
        nothing if the deployment's own door answers differently — a probe could
        then sort real collection codes from invented ones by reading the shape
        of the reply.
        """
        popped = api_client.post(POP_IN_URL, {"email": "one@test.com"}, format="json")
        joined = api_client.post(
            JOIN_URL,
            {"email": "two@test.com", "collection_code": public_collection.code},
            format="json",
        )

        assert popped.status_code == joined.status_code
        assert popped.data == joined.data

    def test_the_product_endpoint_still_refuses_what_it_always_refused(self, api_client):
        """Installing this app must not turn /auth/join/ into an open door too.

        It is the standalone's endpoint, still shipped, and a bare email there
        must go on creating nothing — otherwise the app has changed the product
        instead of adding to it.
        """
        response = api_client.post(JOIN_URL, {"email": "nobody@test.com"}, format="json")

        assert response.status_code == 200
        assert not User.objects.filter(email="nobody@test.com").exists()

    def test_a_malformed_email_is_still_a_400(self, api_client):
        response = api_client.post(POP_IN_URL, {"email": "not-an-email"}, format="json")

        assert response.status_code == 400

"""The open-door endpoint creates nothing until it knows where the person is going.

`POST /auth/join/` used to `get_or_create` the user first and work out the
destination afterwards. That ordering made it an **open registration endpoint**
on a product that is otherwise invite-only: a POST carrying nothing but an email
minted a real account, and on any deployment without onboarding collections — a
fresh install, anyone who never ran `seed_demo` — that account joined nothing
and led nowhere. Nothing in the response ever said so, in either direction.

The fix is an ordering, not a new rule: resolve the target first, and only then
create. What must not change while doing it is the **unified response**, which
is the entire anti-enumeration guarantee of this endpoint — the refusal has to
be indistinguishable from the success, or the endpoint becomes an oracle for
which addresses, tokens and collection codes exist.

So these tests come in pairs: something did not happen, *and* the answer looks
exactly like the one where it did.
"""

import pytest
from django.core import mail

from core.models import RSVP, Collection, User

URL = "/api/v1/auth/join/"


@pytest.fixture
def onboarding_collection(db, user):
    return Collection.objects.create(code="ONBHRD", owner=user, headline="Demo", is_onboarding=True)


@pytest.mark.django_db
class TestNothingToJoinCreatesNothing:
    def test_a_bare_email_creates_no_account(self, api_client):
        """No token, no code, and nowhere to land: the door does not open.

        This is the case that made the endpoint a registration door. It is also
        the shape a script would use to mint accounts in bulk.
        """
        response = api_client.post(URL, {"email": "nobody@test.com"}, format="json")

        assert response.status_code == 200
        assert not User.objects.filter(email="nobody@test.com").exists()

    def test_it_creates_no_rsvp_and_sends_no_mail(self, api_client):
        """Not merely "no user": no login credential and no mail either.

        An RSVP is a working magic link. Minting one for an address that joined
        nothing would hand out a session in exchange for typing an email, which
        is the same hole one layer down.
        """
        api_client.post(URL, {"email": "nobody@test.com"}, format="json")

        assert not RSVP.objects.filter(user_email="nobody@test.com").exists()
        assert mail.outbox == []

    def test_an_existing_account_is_not_touched_either(self, api_client, user):
        """A known address is not a target. It gets the same nothing.

        Otherwise the endpoint answers differently for registered and
        unregistered addresses — by sending mail to one of them — and becomes
        the account oracle the unified response exists to prevent.
        """
        api_client.post(URL, {"email": user.email}, format="json")

        assert not RSVP.objects.filter(user_code=user).exists()
        assert mail.outbox == []


@pytest.mark.django_db
class TestTheAnswerIsAlwaysTheSame:
    def test_refusing_and_joining_are_byte_for_byte_identical(self, api_client, public_collection):
        """The whole point. Same status, same body, both directions.

        Compared as whole responses rather than by asserting a message, so a
        later edit that adds a field — a reason, a flag, a "user_created" — to
        one path and not the other fails here instead of quietly reopening the
        oracle.
        """
        joined = api_client.post(
            URL,
            {"email": "joiner@test.com", "collection_code": public_collection.code},
            format="json",
        )
        refused = api_client.post(URL, {"email": "nobody@test.com"}, format="json")

        assert refused.status_code == joined.status_code
        assert refused.data == joined.data

    def test_a_private_collection_code_is_answered_like_a_public_one(self, api_client, collection):
        """A PRIVATE code is not a way in, and must not be a way to find out either.

        `collection` is PRIVATE by default. Naming it gets the same answer as
        naming nothing — so the endpoint cannot be used to sort real collection
        codes from invented ones, nor public ones from private.
        """
        response = api_client.post(
            URL, {"email": "prober@test.com", "collection_code": collection.code}, format="json"
        )

        assert response.status_code == 200
        assert not User.objects.filter(email="prober@test.com").exists()
        assert not collection.invites.filter(email="prober@test.com").exists()


@pytest.mark.django_db
class TestARealTargetStillWorks:
    """The hardening must cost the two doors that are actual product nothing."""

    def test_a_public_collection_code_joins_and_mails(self, api_client, public_collection):
        response = api_client.post(
            URL,
            {"email": "joiner@test.com", "collection_code": public_collection.code},
            format="json",
        )

        assert response.status_code == 200
        joiner = User.objects.get(email="joiner@test.com")
        assert public_collection.invites.filter(code=joiner.code).exists()
        assert RSVP.objects.filter(user_code=joiner, target_code=public_collection.code).exists()
        assert len(mail.outbox) == 1

    def test_the_onboarding_fallback_still_works_where_there_is_one(
        self, api_client, onboarding_collection
    ):
        """With somewhere to land, a bare email behaves exactly as it always did.

        The ordering changed; the rule did not. What used to run unconditionally
        now runs when there is a destination — and an onboarding collection is
        one.
        """
        response = api_client.post(URL, {"email": "demo@test.com"}, format="json")

        assert response.status_code == 200
        demo_user = User.objects.get(email="demo@test.com")
        assert onboarding_collection.invites.filter(code=demo_user.code).exists()
        assert len(mail.outbox) == 1

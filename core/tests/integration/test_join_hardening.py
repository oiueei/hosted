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
from django.core.cache import caches
from django.test import override_settings

from core.models import RSVP, Collection, User

URL = "/api/v1/auth/join/"


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


@pytest.mark.django_db
class TestOneCollectionCannotBeUsedAsAMailRelay:
    """`COLLECTION_JOINS_PER_DAY` — the cap on the door that needs no account.

    Neither way in here is secret: a PUBLIC collection's code is printed in its
    own URL, and a share token exists to be passed around. So anyone could ask
    the deployment to mail a magic link to any address they typed, which is a
    relay pointed at the operator's sending domain — and the two rate limits on
    the view do not reach it. They cap one IP (5/min) and one victim (5/hour);
    the attack is a hundred IPs mailing a hundred strangers once each.

    `INVITE_EMAILS_PER_DAY` did not cover it either: that counts what an
    *account* sends through the owner's invite routes, and this door has no
    account behind it. These tests are about the counter that finally does.
    """

    # RATELIMIT_ENABLE is off in the test settings and the quota follows it, so
    # switch it on with a local-memory cache the way test_invite_quota.py does.
    # Every test below stays under the view's own 5/min per-IP limit.
    QUOTA_SETTINGS = {
        "RATELIMIT_ENABLE": True,
        "CACHES": {
            "default": {
                "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
                "LOCATION": "join-quota-test",
            }
        },
    }

    @staticmethod
    def _join(client, collection, email):
        return client.post(URL, {"email": email, "collection_code": collection.code}, format="json")

    @override_settings(**QUOTA_SETTINGS, COLLECTION_JOINS_PER_DAY=2)
    def test_a_collection_stops_admitting_people_once_its_day_is_spent(
        self, api_client, public_collection
    ):
        caches["default"].clear()
        for email in ("first@test.com", "second@test.com"):
            assert self._join(api_client, public_collection, email).status_code == 200
        assert len(mail.outbox) == 2

        self._join(api_client, public_collection, "third@test.com")

        # Nothing created and nothing sent — the whole point is that the third
        # stranger is never mailed from the operator's domain.
        assert len(mail.outbox) == 2
        assert not User.objects.filter(email="third@test.com").exists()
        assert not RSVP.objects.filter(user_email="third@test.com").exists()
        assert not public_collection.invites.filter(email="third@test.com").exists()

    @override_settings(**QUOTA_SETTINGS, COLLECTION_JOINS_PER_DAY=1)
    def test_the_refusal_is_indistinguishable_from_a_join(self, api_client, public_collection):
        """It has to be, or the cap becomes the oracle the endpoint avoids.

        "This collection is over its limit" would confirm that the code names a
        real, joinable collection — exactly what every other refusal here
        withholds. Compared as whole responses, like the no-target case.
        """
        caches["default"].clear()
        joined = self._join(api_client, public_collection, "joiner@test.com")

        refused = self._join(api_client, public_collection, "refused@test.com")

        assert refused.status_code == joined.status_code
        assert refused.data == joined.data

    @override_settings(**QUOTA_SETTINGS, COLLECTION_JOINS_PER_DAY=1)
    def test_one_collection_running_out_does_not_close_another(self, api_client, user):
        """Why the counter is keyed per collection and not per deployment.

        A deployment-wide counter would let anyone shut joining off for every
        group on the instance by spending it on one — a denial of service handed
        to the attacker in the name of stopping a relay.
        """
        caches["default"].clear()
        abused = Collection.objects.create(
            code="ABUSED", owner=user, headline="A", visibility=Collection.Visibility.PUBLIC
        )
        bystander = Collection.objects.create(
            code="OTHERC", owner=user, headline="B", visibility=Collection.Visibility.PUBLIC
        )

        self._join(api_client, abused, "one@test.com")
        self._join(api_client, abused, "two@test.com")  # spent: refused
        self._join(api_client, bystander, "three@test.com")

        assert not User.objects.filter(email="two@test.com").exists()
        assert bystander.invites.filter(email="three@test.com").exists()

    @override_settings(**QUOTA_SETTINGS)
    def test_unset_means_no_cap_at_all(self, api_client, public_collection):
        """The standalone default. A share link pasted into a group chat can
        legitimately bring in far more people than any number we could pick, so
        upstream picks none and the operator sets their own."""
        caches["default"].clear()
        for email in ("a@test.com", "b@test.com", "c@test.com"):
            assert self._join(api_client, public_collection, email).status_code == 200

        assert len(mail.outbox) == 3
        assert public_collection.invites.count() == 3

    @override_settings(
        RATELIMIT_ENABLE=False,
        CACHES={
            "default": {
                "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
                "LOCATION": "join-quota-layer-off",
            }
        },
        COLLECTION_JOINS_PER_DAY=1,
    )
    def test_turning_the_rate_limiting_layer_off_turns_this_cap_off_with_it(
        self, api_client, public_collection
    ):
        """One switch, not two — the promise `_join_quota_cap` makes in prose.

        `RATELIMIT_ENABLE` is what a developer or a test run flips to stop every
        counter in the product; the join cap follows it deliberately, so nobody
        has to discover that this one guard needs disabling separately. The
        combination below — layer off, a cap still configured — is a real
        deployment state (an operator turning limits off for an afternoon
        without editing every var) and no test covered it.

        A scoped mutation run is what surfaced it: three mutants that made the
        cap ignore `RATELIMIT_ENABLE` entirely all survived a suite with this
        module at 100% line coverage, because every test that set a cap also had
        the layer on.
        """
        caches["default"].clear()

        for email in ("first@test.com", "second@test.com", "third@test.com"):
            assert self._join(api_client, public_collection, email).status_code == 200

        # A cap of 1 would have stopped the second. The layer is off, so it does
        # not apply and all three are genuinely admitted — not merely answered
        # with the unified 200, which a refusal returns too.
        assert public_collection.invites.count() == 3
        assert len(mail.outbox) == 3

"""Integration tests for login-to-act auto-join on PUBLIC collections (#5, phase 3).

A visitor who tries to act on a PUBLIC collection submits their email plus the
collection code to pop-in; on submission they are added to that collection's
invitees and emailed a magic link. The code only joins PUBLIC, ACTIVE
collections — never a PRIVATE one — and an unknown/non-public code is silently
ignored (same unified response, no enumeration oracle).
"""

import pytest
from django.core import mail
from rest_framework.test import APIClient

from core.models import RSVP, Collection, Event, User

JOIN_URL = "/api/v1/auth/join/"


@pytest.fixture
def join_setup(db):
    owner = User.objects.create(code="JNOWN1", email="jnown@test.com", name="Owner")
    public = Collection.objects.create(
        code="JPUB01",
        owner=owner,
        headline="Open community",
        status="ACTIVE",
        visibility=Collection.Visibility.PUBLIC,
    )
    private = Collection.objects.create(
        code="JPRV01",
        owner=owner,
        headline="Closed group",
        status="ACTIVE",
        visibility=Collection.Visibility.PRIVATE,
    )
    inactive_public = Collection.objects.create(
        code="JINA01",
        owner=owner,
        headline="Archived",
        status="INACTIVE",
        visibility=Collection.Visibility.PUBLIC,
    )
    onboarding = Collection.objects.create(
        code="JONB01",
        owner=owner,
        headline="Demo",
        status="ACTIVE",
        is_onboarding=True,
    )
    return {
        "public": public,
        "private": private,
        "inactive_public": inactive_public,
        "onboarding": onboarding,
        "anon": APIClient(),
    }


@pytest.mark.django_db
class TestPublicAutoJoin:
    def test_public_code_adds_user_and_sends_magic_link(self, join_setup):
        resp = join_setup["anon"].post(
            JOIN_URL,
            {"email": "visitor@test.com", "collection_code": "JPUB01"},
            format="json",
        )
        assert resp.status_code == 200
        user = User.objects.get(email="visitor@test.com")
        assert join_setup["public"].invites.filter(code=user.code).exists()
        # A magic-link RSVP was issued so the visitor can log in and then act.
        assert RSVP.objects.filter(user_code=user, action=RSVP.Action.MAGIC_LINK).exists()

    def test_public_code_does_not_also_join_onboarding(self, join_setup):
        join_setup["anon"].post(
            JOIN_URL,
            {"email": "visitor2@test.com", "collection_code": "JPUB01"},
            format="json",
        )
        user = User.objects.get(email="visitor2@test.com")
        assert join_setup["public"].invites.filter(code=user.code).exists()
        assert not join_setup["onboarding"].invites.filter(code=user.code).exists()

    def test_private_code_does_not_join(self, join_setup):
        """A PRIVATE collection's code buys nothing — not membership, not an account.

        The code of a private group circulates: it is in every URL its members
        ever paste. It must never be a way in, and since nothing is created
        without a valid target, it is not a way to mint an account either.
        """
        resp = join_setup["anon"].post(
            JOIN_URL,
            {"email": "probe@test.com", "collection_code": "JPRV01"},
            format="json",
        )
        assert resp.status_code == 200
        assert not User.objects.filter(email="probe@test.com").exists()
        assert not join_setup["private"].invites.filter(email="probe@test.com").exists()

    def test_inactive_public_code_does_not_join(self, join_setup):
        resp = join_setup["anon"].post(
            JOIN_URL,
            {"email": "inactive@test.com", "collection_code": "JINA01"},
            format="json",
        )
        assert resp.status_code == 200
        assert not User.objects.filter(email="inactive@test.com").exists()
        assert not join_setup["inactive_public"].invites.filter(email="inactive@test.com").exists()

    def test_unknown_code_is_ignored(self, join_setup):
        """Answered exactly like a real one, and nothing happens behind it."""
        resp = join_setup["anon"].post(
            JOIN_URL,
            {"email": "ghost@test.com", "collection_code": "NOPE00"},
            format="json",
        )
        assert resp.status_code == 200
        assert not User.objects.filter(email="ghost@test.com").exists()

    def test_existing_user_can_join_via_public_code(self, join_setup):
        existing = User.objects.create(code="JEXST1", email="member@test.com", name="Member")
        resp = join_setup["anon"].post(
            JOIN_URL,
            {"email": "member@test.com", "collection_code": "JPUB01"},
            format="json",
        )
        assert resp.status_code == 200
        assert join_setup["public"].invites.filter(code=existing.code).exists()

    def test_public_code_stamps_target_on_rsvp(self, join_setup):
        # The magic-link RSVP carries the collection as target_code so that, after
        # verifying, the visitor is redirected straight back to it (login-to-act).
        join_setup["anon"].post(
            JOIN_URL,
            {"email": "redir@test.com", "collection_code": "JPUB01"},
            format="json",
        )
        user = User.objects.get(email="redir@test.com")
        rsvp = RSVP.objects.get(user_code=user, action=RSVP.Action.MAGIC_LINK)
        assert rsvp.target_code == "JPUB01"

    def test_verify_public_join_returns_invited_collection(self, join_setup):
        # End-to-end #6: after pop-in via a public code, verifying the magic link
        # returns invited_collection so the SPA drops the visitor straight onto the
        # collection they came to act on — not the generic /welcome.
        join_setup["anon"].post(
            JOIN_URL,
            {"email": "roundtrip@test.com", "collection_code": "JPUB01"},
            format="json",
        )
        user = User.objects.get(email="roundtrip@test.com")
        rsvp = RSVP.objects.get(user_code=user, action=RSVP.Action.MAGIC_LINK)

        resp = APIClient().get(f"/api/v1/auth/verify/{rsvp.token}/")
        assert resp.status_code == 200
        assert resp.data["action"] == "MAGIC_LINK"
        assert resp.data["invited_collection"] == "JPUB01"
        assert resp.data["landing"] == "collection"
        assert resp.data["collection"] == "JPUB01"

    def test_a_targetless_join_still_lands_on_welcome(self, join_setup, user):
        """The landing contract a deployment with an open door depends on.

        Nothing in the standalone produces this RSVP any more — every join here
        carries a collection — so it is built directly rather than through the
        endpoint. It is kept, and kept tested, because a deployment that adds
        its own open door (`DEPLOYMENT_URLCONFS`) stamps exactly this shape, and
        `VerifyLinkView` is a shared file it must never have to edit.
        """
        rsvp = RSVP.objects.create(
            user_code=user,
            user_email=user.email,
            action=RSVP.Action.MAGIC_LINK,
            origin=RSVP.Origin.POPIN,
        )

        resp = APIClient().get(f"/api/v1/auth/verify/{rsvp.token}/")

        assert resp.status_code == 200
        assert "invited_collection" not in resp.data
        assert resp.data["landing"] == "welcome"

    def test_public_code_magic_link_subject_names_collection(self, join_setup):
        # Joining a PUBLIC collection by code names it in the magic-link subject.
        mail.outbox.clear()
        join_setup["anon"].post(
            JOIN_URL,
            {"email": "subj@test.com", "collection_code": "JPUB01"},
            format="json",
        )
        assert "Open community" in mail.outbox[0].subject


@pytest.mark.django_db
class TestMemberJoinedIsLoggedOncePerJoin:
    """One person joining once must read as one join.

    The M2M add is idempotent and joining re-runs on every login-to-act visit, so
    logging MEMBER_JOINED unconditionally counted a returning member as a fresh
    join each time — inflating member-join counts and the guest→creator funnel in
    any funnel report, which reads one MEMBER_JOINED per person as the entry point.
    """

    EMAIL = "rejoin@test.com"

    def _pop_in(self, join_setup):
        return join_setup["anon"].post(
            JOIN_URL,
            {"email": self.EMAIL, "collection_code": "JPUB01"},
            format="json",
        )

    def _joins(self, user, collection):
        return Event.objects.filter(
            kind=Event.Kind.MEMBER_JOINED,
            actor_code=user.code,
            collection_code=collection.code,
        ).count()

    def test_a_first_join_is_logged(self, join_setup):
        self._pop_in(join_setup)

        user = User.objects.get(email=self.EMAIL)
        assert self._joins(user, join_setup["public"]) == 1

    def test_re_entering_as_an_existing_member_logs_nothing_new(self, join_setup):
        # Three visits, one member: the login-to-act pop-in fires on every attempt
        # to act on a public collection, not just the first.
        self._pop_in(join_setup)
        self._pop_in(join_setup)
        self._pop_in(join_setup)

        user = User.objects.get(email=self.EMAIL)
        assert self._joins(user, join_setup["public"]) == 1
        assert join_setup["public"].invites.filter(code=user.code).exists()

    def test_rejoining_after_leaving_is_a_real_join_and_logs_again(self, join_setup):
        self._pop_in(join_setup)
        user = User.objects.get(email=self.EMAIL)

        # Leaving takes the user out of invites, so coming back is a genuine join.
        join_setup["public"].invites.remove(user)
        self._pop_in(join_setup)

        assert self._joins(user, join_setup["public"]) == 2

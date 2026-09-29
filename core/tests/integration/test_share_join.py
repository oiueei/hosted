"""``POST /api/v1/share/{token}/join/`` — accepting a share invitation with a session.

``SharePage`` used to ask for an email even when the reader was signed in: email,
inbox, link, back. In a neighbourhood the same people belong to several groups
and this link is the main viral route, so it was a round trip for the people who
use it most. The credential here is the **token** (the twin of
``POST /collections/{code}/join/``, whose credential is the collection being
PUBLIC), so what these tests hold is the edge of that credential: what a token
opens, what it must never reveal, and that a door which joins people goes
through the one funnel every other door uses.
"""

import pytest
from django.core import mail
from django.core.cache import caches
from django.test import override_settings
from rest_framework.test import APIClient

from core.models import RSVP, Collection, Event, User

TOKEN = "tok_shared_group_0123"
URL = "/api/v1/share/{}/join/"
DOC_ID = "oiueei/documents/welcome-doc-1"


def _post(client, token=TOKEN):
    return client.post(URL.format(token))


def _member_joined(collection, user):
    return Event.objects.filter(
        kind=Event.Kind.MEMBER_JOINED, collection_code=collection.code, actor_code=user.code
    )


@pytest.fixture
def owner(db):
    return User.objects.create(code="SHOWN1", email="shown@test.com", name="Owner")


@pytest.fixture
def shared(owner):
    """A PRIVATE collection its owner has shared by link: the token is the way in."""
    return Collection.objects.create(
        code="SHARE1",
        owner=owner,
        headline="The street",
        status=Collection.Status.ACTIVE,
        visibility=Collection.Visibility.PRIVATE,
        share_token=TOKEN,
    )


@pytest.fixture
def signed_in(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.mark.django_db
class TestAcceptingWithASession:
    def test_the_token_joins_the_reader_and_answers_with_the_group(self, signed_in, user, shared):
        res = _post(signed_in)

        assert res.status_code == 200
        assert res.data == {"collection": shared.code, "joined": True}
        assert shared.invites.filter(code=user.code).exists()
        # Counted as the share door, so a report over the Event log can say which
        # of the doors actually brings people in.
        joined = _member_joined(shared, user)
        assert joined.count() == 1
        assert joined.first().source == Event.Source.SHARE

    def test_it_makes_no_account_and_no_link_because_there_is_a_session(self, signed_in, shared):
        users_before = User.objects.count()

        _post(signed_in)

        assert User.objects.count() == users_before
        assert not RSVP.objects.exists()

    def test_the_answer_never_carries_the_token(self, signed_in, shared):
        """The token is a bearer credential; nothing in the answer hands it back,
        or would let a member who joined by it pass it on from the response."""
        res = _post(signed_in)

        assert TOKEN not in res.content.decode()
        assert set(res.data) == {"collection", "joined"}

    def test_repeating_it_neither_joins_twice_nor_resends_the_welcome_document(
        self, signed_in, user, shared
    ):
        shared.welcome_doc = DOC_ID
        shared.save()

        first = _post(signed_in)
        second = _post(signed_in)

        assert first.data["joined"] is True
        assert second.status_code == 200
        assert second.data == {"collection": shared.code, "joined": False}
        assert _member_joined(shared, user).count() == 1
        assert len([m for m in mail.outbox if DOC_ID in m.body]) == 1

    def test_it_goes_through_the_funnel_every_other_door_uses(self, signed_in, user, shared):
        """A door that grew its own ``invites.add()`` — the obvious way to write
        this — would admit the member and silently never send them the rules."""
        shared.welcome_doc = DOC_ID
        shared.save()

        _post(signed_in)

        sent = [m for m in mail.outbox if DOC_ID in m.body]
        assert len(sent) == 1
        assert sent[0].to == [user.email]

    def test_the_owner_trying_their_own_link_lands_on_their_collection(self, owner, shared):
        client = APIClient()
        client.force_authenticate(user=owner)

        res = _post(client)

        assert res.status_code == 200
        assert res.data == {"collection": shared.code, "joined": False}
        assert not _member_joined(shared, owner).exists()

    def test_a_co_curator_is_told_they_are_already_in(self, signed_in, user, shared):
        # Co-curators live in ``invites`` (``co_owners`` is a subset of it).
        shared.invites.add(user)
        shared.co_owners.add(user)

        res = _post(signed_in)

        assert res.data == {"collection": shared.code, "joined": False}
        assert not _member_joined(shared, user).exists()


@pytest.mark.django_db
class TestWhatTheTokenDoesNotOpen:
    def test_an_unknown_a_revoked_and_an_inactive_token_answer_the_same_404(
        self, signed_in, shared, owner
    ):
        """One generic 404 for all three, as ``SharePreviewView`` answers them:
        the token is the credential, so a refusal must say nothing about *why*."""
        unknown = _post(signed_in, "no_such_token_at_all")

        # Revoked: what ``DELETE /collections/{code}/share-link/`` does to the token.
        shared.share_token = None
        shared.save()
        revoked = _post(signed_in)

        archived = Collection.objects.create(
            code="SHARE3",
            owner=owner,
            headline="Archived",
            status=Collection.Status.INACTIVE,
            share_token="tok_inactive_grp_0123",
        )
        inactive = _post(signed_in, "tok_inactive_grp_0123")

        assert unknown.status_code == revoked.status_code == inactive.status_code == 404
        assert unknown.content == revoked.content == inactive.content
        assert not shared.invites.exists()
        assert not archived.invites.exists()

    def test_a_revoked_token_stops_working_the_moment_it_is_revoked(self, signed_in, user, shared):
        shared.share_token = None
        shared.save()

        res = _post(signed_in)

        assert res.status_code == 404
        assert not shared.invites.filter(code=user.code).exists()

    def test_a_public_group_code_is_not_a_token(self, signed_in, user, owner):
        """The token is looked up as a token. A collection's *code* — which is not
        a secret for a PUBLIC group — must never open this door as one."""
        public = Collection.objects.create(
            code="PUBTOK",
            owner=owner,
            headline="Open",
            visibility=Collection.Visibility.PUBLIC,
            share_token="tok_for_the_public_grp",
        )

        res = _post(signed_in, public.code)

        assert res.status_code == 404
        assert not public.invites.filter(code=user.code).exists()

    def test_without_a_session_it_is_a_401_and_joins_nobody(self, shared):
        res = _post(APIClient())

        assert res.status_code == 401
        assert shared.invites.count() == 0


@pytest.mark.django_db
class TestTheOperatorsCeiling:
    @override_settings(
        RATELIMIT_ENABLE=True,
        CACHES={
            "default": {
                "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
                "LOCATION": "share-join-quota",
            }
        },
        COLLECTION_JOINS_PER_DAY=1,
    )
    def test_a_collection_that_has_taken_its_days_joins_refuses_the_next_and_nobody_joins(
        self, user, user2, shared
    ):
        """A ceiling that only stopped strangers would be one anyone with an account
        could walk around, and an account costs a free mailbox. Two people, each
        with their own client: a shared ``APIClient`` would rebind the first."""
        caches["default"].clear()
        first, second = APIClient(), APIClient()
        first.force_authenticate(user=user)
        second.force_authenticate(user=user2)

        assert _post(first).status_code == 200
        res = _post(second)

        assert res.status_code == 429
        assert res.data["detail"] == "This collection has taken today's joins. Try again tomorrow."
        assert not shared.invites.filter(code=user2.code).exists()
        assert not _member_joined(shared, user2).exists()

    @override_settings(
        RATELIMIT_ENABLE=True,
        CACHES={
            "default": {
                "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
                "LOCATION": "share-join-quota",
            }
        },
        COLLECTION_JOINS_PER_DAY=1,
    )
    def test_a_full_day_still_lets_the_owner_and_a_member_in(self, user, user2, owner, shared):
        """The daily ceiling stops whoever is not in yet, not someone already in: a
        member opening the link again, or the curator trying their own link on a
        busy day, is answered as always and never told a group they belong to has
        "taken today's joins". One client per person: the fixtures share one."""
        caches["default"].clear()
        member, stranger, founder = APIClient(), APIClient(), APIClient()
        member.force_authenticate(user=user)
        stranger.force_authenticate(user=user2)
        founder.force_authenticate(user=owner)

        # The one join the day allows, then proof that the day really is full.
        assert _post(member).data == {"collection": shared.code, "joined": True}
        assert _post(stranger).status_code == 429

        again = _post(member)
        from_the_owner = _post(founder)

        assert (again.status_code, again.data) == (
            200,
            {"collection": shared.code, "joined": False},
        )
        assert (from_the_owner.status_code, from_the_owner.data) == (
            200,
            {"collection": shared.code, "joined": False},
        )
        assert _member_joined(shared, user).count() == 1
        assert not shared.invites.filter(code=user2.code).exists()

    @override_settings(
        RATELIMIT_ENABLE=True,
        CACHES={
            "default": {
                "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
                "LOCATION": "share-join-ratelimit",
            }
        },
    )
    def test_it_is_limited_to_30_an_hour_per_user(self, signed_in, shared):
        caches["default"].clear()

        statuses = [_post(signed_in).status_code for _ in range(31)]

        assert statuses[0] == 200  # joins…
        assert set(statuses[1:30]) == {200}  # …then idempotent answers…
        assert statuses[30] == 429  # …and the 31st in the hour is refused

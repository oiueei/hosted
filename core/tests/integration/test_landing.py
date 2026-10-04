"""
Post-login landing (O3): where VerifyLinkView sends the user after a magic link.

The destination used to be a client-side ``seenWelcome`` localStorage heuristic —
and since logout clears that key, every re-login looked like a first visit and
dumped returning users on the new-visitor page. It is now decided server-side from
the RSVP's target, the page they were heading for and the user's collections —
leaving out the demonstration ones (CA, 2026-10-04: one real group → that group,
anything else → Home, whichever door the link came in by).
"""

import pytest
from rest_framework.test import APIClient

from core.models import RSVP, Collection, User

VERIFY_URL = "/api/v1/auth/verify/{}/"
REQUEST_LINK_URL = "/api/v1/auth/request-link/"


def _magic_link(user, origin=RSVP.Origin.LOGIN, target_code="", context=None):
    return RSVP.objects.create(
        user_code=user,
        user_email=user.email,
        action=RSVP.Action.MAGIC_LINK,
        origin=origin,
        target_code=target_code,
        context=context or {},
    )


def _verify(rsvp):
    return APIClient().get(VERIFY_URL.format(rsvp.token))


@pytest.mark.django_db
class TestMagicLinkLanding:
    def test_a_targetless_join_link_with_no_group_lands_on_home(self, user2):
        """A deployment with its own open door stamps POPIN with no collection.

        Built directly: nothing here stamps POPIN without a collection any more.
        It used to be sent to a "welcome" page of the deployment's own; it now
        gets the same answer as anyone else, and with no group that is Home.
        """
        res = _verify(_magic_link(user2, origin=RSVP.Origin.POPIN))

        assert res.status_code == 200
        assert res.data["landing"] == "home"
        assert "collection" not in res.data

    def test_link_carrying_a_collection_lands_on_it(self, user, collection):
        # A share-token / public-collection join: they joined that collection to
        # get here, so the origin doesn't matter — the target wins.
        res = _verify(_magic_link(user, origin=RSVP.Origin.POPIN, target_code=collection.code))

        assert res.data["landing"] == "collection"
        assert res.data["collection"] == collection.code
        assert res.data["invited_collection"] == collection.code

    def test_link_carrying_an_inactive_collection_falls_back(self, user, collection):
        # The collection went INACTIVE between the join and the click — landing
        # there would 403. The general rule takes over instead, and an INACTIVE
        # group does not count, so it is Home.
        collection.status = Collection.Status.INACTIVE
        collection.save()
        res = _verify(_magic_link(user, origin=RSVP.Origin.POPIN, target_code=collection.code))

        assert res.data["landing"] == "home"
        assert "collection" not in res.data
        assert "invited_collection" not in res.data

    def test_login_with_exactly_one_collection_lands_on_it(self, user, collection):
        # `collection` is this user's only one.
        res = _verify(_magic_link(user))

        assert res.data["landing"] == "collection"
        assert res.data["collection"] == collection.code
        # A plain login carries no target, so the invitation marker stays absent.
        assert "invited_collection" not in res.data

    def test_login_with_one_invited_collection_lands_on_it(self, user, user2, collection):
        # Invited counts the same as owned: it's still their only collection.
        collection.invites.add(user2)
        res = _verify(_magic_link(user2))

        assert res.data["landing"] == "collection"
        assert res.data["collection"] == collection.code

    def test_login_with_several_collections_lands_on_home(self, user, collection):
        Collection.objects.create(code="SECOND", owner=user, headline="Second one")
        res = _verify(_magic_link(user))

        assert res.data["landing"] == "home"
        assert "collection" not in res.data

    def test_login_with_no_collections_lands_on_home(self, user2):
        res = _verify(_magic_link(user2))

        assert res.data["landing"] == "home"

    def test_inactive_collections_do_not_count(self, user, collection):
        collection.status = Collection.Status.INACTIVE
        collection.save()
        res = _verify(_magic_link(user))

        assert res.data["landing"] == "home"

    def test_legacy_link_without_an_origin_is_treated_as_a_login(self, user, collection):
        # Magic links minted before RSVP.origin existed have origin="" — they are
        # returning users, so they follow the login rule.
        res = _verify(_magic_link(user, origin=""))

        assert res.data["landing"] == "collection"
        assert res.data["collection"] == collection.code


def _group(code, owner, **fields):
    """A collection, ACTIVE unless told otherwise."""
    return Collection.objects.create(code=code, owner=owner, headline=f"Group {code}", **fields)


def _demo(owner, count=1):
    """The demonstration collections an open door joins people to."""
    return [_group(f"DEMO{n:02d}", owner, is_onboarding=True) for n in range(count)]


@pytest.mark.django_db
class TestOnlyRealGroupsDecideTheLanding:
    """One real group → that group; none, or several → Home (CA, 2026-10-04).

    "Real" leaves out the demonstration collections (``is_onboarding``). The
    answer is the same whichever door the link came in by, so each case that is
    about the groups runs for both a ``/login`` link and a ``/popin`` one.
    """

    ORIGINS = [RSVP.Origin.LOGIN, RSVP.Origin.POPIN]

    @pytest.fixture
    def founder(self, user2):
        """Somebody else, who owns the demo and the groups the others belong to."""
        return user2

    @pytest.mark.parametrize("origin", ORIGINS)
    def test_one_real_group_among_demos_lands_on_the_real_one(self, user, founder, origin):
        real = _group("REAL01", founder)
        real.invites.add(user)
        for demo in _demo(founder, count=3):
            demo.invites.add(user)

        res = _verify(_magic_link(user, origin=origin))

        assert res.data["landing"] == "collection"
        assert res.data["collection"] == real.code

    @pytest.mark.parametrize("origin", ORIGINS)
    def test_two_real_groups_land_on_home_whatever_the_demos(self, user, founder, origin):
        for code in ("REAL01", "REAL02"):
            _group(code, founder).invites.add(user)
        for demo in _demo(founder, count=2):
            demo.invites.add(user)

        res = _verify(_magic_link(user, origin=origin))

        assert res.data["landing"] == "home"
        assert "collection" not in res.data

    @pytest.mark.parametrize("origin", ORIGINS)
    def test_only_demonstration_groups_land_on_home(self, user, founder, origin):
        # Even a single demo: it is not a group of theirs to be taken to.
        for demo in _demo(founder):
            demo.invites.add(user)

        res = _verify(_magic_link(user, origin=origin))

        assert res.data["landing"] == "home"
        assert "collection" not in res.data

    @pytest.mark.parametrize("origin", ORIGINS)
    def test_a_demonstration_group_they_own_is_not_counted_either(self, user, origin):
        _demo(user)

        res = _verify(_magic_link(user, origin=origin))

        assert res.data["landing"] == "home"

    @pytest.mark.parametrize("origin", ORIGINS)
    def test_a_co_curator_of_one_real_group_lands_on_it(self, user, founder, origin):
        real = _group("REAL01", founder)
        real.invites.add(user)
        real.co_owners.add(user)

        res = _verify(_magic_link(user, origin=origin))

        assert res.data["landing"] == "collection"
        assert res.data["collection"] == real.code

    @pytest.mark.parametrize("origin", ORIGINS)
    def test_the_owner_of_one_real_group_lands_on_it(self, user, origin):
        real = _group("REAL01", user)
        _demo(user, count=2)

        res = _verify(_magic_link(user, origin=origin))

        assert res.data["landing"] == "collection"
        assert res.data["collection"] == real.code

    @pytest.mark.parametrize("origin", ORIGINS)
    def test_an_inactive_group_does_not_count_so_the_other_one_is_the_only_one(self, user, origin):
        active = _group("REAL01", user)
        _group("REAL02", user, status=Collection.Status.INACTIVE)

        res = _verify(_magic_link(user, origin=origin))

        assert res.data["landing"] == "collection"
        assert res.data["collection"] == active.code

    def test_a_group_that_is_both_owned_and_invited_counts_once(self, user):
        # The owner can also sit in `invites`; the join must not double the row.
        real = _group("REAL01", user)
        real.invites.add(user)

        res = _verify(_magic_link(user))

        assert res.data["landing"] == "collection"
        assert res.data["collection"] == real.code


def _request_link(email, **body):
    """Ask for a login link as the SPA does, and hand back (response, the RSVP it minted)."""
    response = APIClient().post(REQUEST_LINK_URL, {"email": email, **body}, format="json")
    return response, RSVP.objects.filter(user_email=email).first()


@pytest.mark.django_db
class TestLoginReturnsToWhereTheyWereGoing:
    """The session ran out on a page; the magic link must bring them back to it.

    Kept on the server (the RSVP), not in browser storage, because the link is
    often opened in another browser than the one that showed ``/login``.
    """

    def test_a_login_with_a_next_lands_on_that_path(self, user):
        _, rsvp = _request_link(user.email, next="/collections/AbC123/things/XyZ789")

        res = _verify(rsvp)

        assert res.status_code == 200
        assert res.data["landing"] == "path"
        assert res.data["path"] == "/collections/AbC123/things/XyZ789"

    def test_next_outranks_the_single_collection_rule(self, user, collection):
        # `collection` is this user's only one: without a next they would land on it.
        _, rsvp = _request_link(user.email, next="/me/edit")

        res = _verify(rsvp)

        assert res.data["landing"] == "path"
        assert res.data["path"] == "/me/edit"
        assert "collection" not in res.data

    @pytest.mark.parametrize(
        "bad_next",
        ["//evil.com", "https://evil.com", "/login", "/", ["/me"], 123],
    )
    def test_a_next_that_is_not_a_same_site_path_is_dropped_and_the_usual_rule_applies(
        self, user, collection, bad_next
    ):
        response, rsvp = _request_link(user.email, next=bad_next)

        assert response.status_code == 200
        assert rsvp.context == {}
        res = _verify(rsvp)
        assert res.data["landing"] == "collection"
        assert res.data["collection"] == collection.code
        assert "path" not in res.data

    def test_the_answer_is_byte_for_byte_the_same_with_and_without_a_next(self, user):
        """A ``next`` must not turn request-link into a probe: not for a registered
        address, not for an unregistered one, and not for a bad value."""
        for email in (user.email, "nobody@test.com"):
            plain, _ = _request_link(email)
            with_next, _ = _request_link(email, next="/collections/AbC123")
            with_bad_next, _ = _request_link(email, next="//evil.com")

            assert plain.status_code == with_next.status_code == with_bad_next.status_code == 200
            assert plain.content == with_next.content == with_bad_next.content

    def test_an_unregistered_email_with_a_next_creates_nothing(self):
        response, rsvp = _request_link("nobody@test.com", next="/collections/AbC123")

        assert response.status_code == 200
        assert rsvp is None
        assert not User.objects.filter(email="nobody@test.com").exists()

    def test_a_bad_next_written_straight_into_the_database_is_not_followed(self, user, collection):
        # Not through request-link: a `context` written by some other route. The
        # click checks again, so it still can't send the session off-site.
        rsvp = _magic_link(user, context={"next": "//evil.com"})

        res = _verify(rsvp)

        assert res.data["landing"] == "collection"
        assert res.data["collection"] == collection.code
        assert "path" not in res.data

    def test_a_legacy_link_with_no_origin_follows_its_next(self, user):
        res = _verify(_magic_link(user, origin="", context={"next": "/my-bookings"}))

        assert res.data["landing"] == "path"
        assert res.data["path"] == "/my-bookings"

    def test_a_join_link_is_never_redirected_by_a_next(self, user2):
        # Whoever walks in by an open door has no session that ran out on a page,
        # so a stray next is not followed: they get the general rule — here, with
        # no group, Home.
        res = _verify(
            _magic_link(user2, origin=RSVP.Origin.POPIN, context={"next": "/my-bookings"})
        )

        assert res.data["landing"] == "home"
        assert "path" not in res.data

    def test_a_join_link_with_a_next_still_goes_to_its_one_real_group(self, user, collection):
        # `collection` is this user's only real group. The next is ignored on a
        # POPIN link, and the group rule is what answers.
        res = _verify(_magic_link(user, origin=RSVP.Origin.POPIN, context={"next": "/my-bookings"}))

        assert res.data["landing"] == "collection"
        assert res.data["collection"] == collection.code
        assert "path" not in res.data

    def test_a_login_link_with_a_next_follows_it_over_a_real_group(self, user, collection):
        # The mirror of the two above: the same next, on a /login link, wins.
        res = _verify(_magic_link(user, context={"next": "/my-bookings"}))

        assert res.data["landing"] == "path"
        assert res.data["path"] == "/my-bookings"


@pytest.mark.django_db
class TestOriginIsStamped:
    def test_request_link_stamps_login(self, api_client, user):
        api_client.post("/api/v1/auth/request-link/", {"email": user.email}, format="json")

        rsvp = RSVP.objects.get(user_code=user, action=RSVP.Action.MAGIC_LINK)
        assert rsvp.origin == RSVP.Origin.LOGIN

    def test_joining_stamps_popin(self, api_client, user):
        """Every join through this endpoint is stamped POPIN, whichever door it came in by.

        Written through a PUBLIC collection rather than a bare email: that is
        one of the two doors that outlive the demo, and the endpoint now needs
        a target before it creates anything.
        """
        public = Collection.objects.create(
            code="LANDPB",
            owner=user,
            headline="Public",
            visibility=Collection.Visibility.PUBLIC,
        )

        api_client.post(
            "/api/v1/auth/join/",
            {"email": "fresh@test.com", "collection_code": public.code},
            format="json",
        )

        rsvp = RSVP.objects.get(user_email="fresh@test.com", action=RSVP.Action.MAGIC_LINK)
        assert rsvp.origin == RSVP.Origin.POPIN


@pytest.mark.django_db
class TestCollectionInviteLanding:
    def test_invite_lands_on_its_collection(self, user2, collection):
        rsvp = RSVP.objects.create(
            user_code=user2,
            user_email=user2.email,
            action=RSVP.Action.COLLECTION_INVITE,
            target_code=collection.code,
        )

        res = _verify(rsvp)

        assert res.data["landing"] == "collection"
        assert res.data["collection"] == collection.code
        assert res.data["invited_collection"] == collection.code

    def test_invite_to_a_deleted_collection_lands_on_home(self, user2):
        rsvp = RSVP.objects.create(
            user_code=user2,
            user_email=user2.email,
            action=RSVP.Action.COLLECTION_INVITE,
            target_code="GONE01",
        )

        res = _verify(rsvp)

        assert res.data["landing"] == "home"

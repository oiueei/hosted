"""Who may run a group on this deployment — the `hosted` app's policy.

**Tests code that is not in the standalone** (see `test_hosted_popin.py` for why
the file sits here). What it protects, in the order it matters:

**The narrowing is real.** Community collections, lending and renting are held
back until somebody has been read and approved. If this quietly stopped
applying, the deployment would be handing out exactly the two things it answers
for, and nothing would look wrong.

**The narrowing is not a wall.** Giving and selling stay open to everyone, an
approved person gets the whole product, and — the part that is easy to get
wrong — a refusal always says where to ask.

**It never contradicts itself.** `GET /auth/me/` and the create endpoints are
computed from one `capabilities()` call, so what the UI offers is what the API
accepts. That equality is asserted across both endpoints rather than assumed.
"""

import pytest
from django.utils import timezone
from rest_framework import status

from core.models import Collection, Thing
from hosted.models import CreatorValidation
from hosted.policy import HostedCreatorPolicy, request_access_url

POLICY = "hosted.policy.HostedCreatorPolicy"
FORM_URL = "/request-access/"


@pytest.fixture(autouse=True)
def hosted_policy(settings):
    """This deployment's policy, on for every test in this file.

    It is deliberately **not** set in `config/settings/development.py`: the whole
    upstream suite runs on those settings, and switching the product's own tests
    to a narrowed policy would have them asserting this deployment's rules
    instead of OIUEEI's. Production sets it; here each test asks for it.
    """
    settings.CREATOR_POLICY = POLICY


def approve(user, **kwargs):
    return CreatorValidation.objects.create(
        user=user,
        who="A neighbour",
        intent="A tool library for the block",
        status=CreatorValidation.Status.APPROVED,
        resolved=timezone.now(),
        **kwargs,
    )


@pytest.mark.django_db
class TestSomebodyWhoHasNotAsked:
    def test_giving_and_selling_are_open_to_them(self, authenticated_client):
        for thing_type in ("GIFT_THING", "SELL_THING"):
            response = authenticated_client.post(
                "/api/v1/things/",
                {"type": thing_type, "headline": "A thing", "thumbnail": "img/x"},
                format="json",
            )
            assert response.status_code == status.HTTP_201_CREATED, thing_type

    def test_a_private_collection_is_open_to_them(self, authenticated_client):
        response = authenticated_client.post(
            "/api/v1/collections/", {"headline": "My shelf"}, format="json"
        )

        assert response.status_code == status.HTTP_201_CREATED

    @pytest.mark.parametrize("thing_type", ["LEND_THING", "RENT_THING"])
    def test_lending_and_renting_are_held_back(self, authenticated_client, thing_type):
        response = authenticated_client.post(
            "/api/v1/things/",
            {"type": thing_type, "headline": "A ladder", "thumbnail": "img/x"},
            format="json",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert not Thing.objects.filter(headline="A ladder").exists()

    def test_a_community_collection_is_held_back(self, authenticated_client):
        response = authenticated_client.post(
            "/api/v1/collections/",
            {"headline": "Mercadillo", "mode": "COMMUNITY"},
            format="json",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert not Collection.objects.filter(headline="Mercadillo").exists()

    def test_the_refusal_says_where_to_ask(self, authenticated_client):
        """A closed door with no handle is the failure this whole app avoids.

        The URL is in the 403 body as well as in `capabilities`, because the API
        is usable without the SPA and a client that only sees the refusal would
        otherwise never learn that asking is possible.
        """
        response = authenticated_client.post(
            "/api/v1/collections/",
            {"headline": "Mercadillo", "mode": "COMMUNITY"},
            format="json",
        )

        assert FORM_URL in str(response.data)

    def test_me_advertises_exactly_the_open_half(self, authenticated_client):
        response = authenticated_client.get("/api/v1/auth/me/")

        assert response.data["capabilities"] == {
            "collection_modes": ["PROPRIETARY"],
            "thing_types": ["GIFT_THING", "SELL_THING"],
            "request_url": FORM_URL,
        }


@pytest.mark.django_db
class TestSomebodyApproved:
    def test_they_get_the_whole_product(self, authenticated_client, user):
        approve(user)

        collection = authenticated_client.post(
            "/api/v1/collections/", {"headline": "Mercadillo", "mode": "COMMUNITY"}, format="json"
        )
        thing = authenticated_client.post(
            "/api/v1/things/",
            {"type": "LEND_THING", "headline": "A ladder", "thumbnail": "img/x"},
            format="json",
        )

        assert collection.status_code == status.HTTP_201_CREATED
        assert thing.status_code == status.HTTP_201_CREATED

    def test_me_stops_offering_anywhere_to_ask(self, authenticated_client, user):
        approve(user)

        capabilities = authenticated_client.get("/api/v1/auth/me/").data["capabilities"]

        assert capabilities["collection_modes"] == list(Collection.Mode.values)
        assert capabilities["thing_types"] == list(Thing.Type.values)
        # Nothing left to request, so the notice must not appear at all.
        assert capabilities["request_url"] is None

    @pytest.mark.parametrize("pending_status", ["PENDING", "REJECTED"])
    def test_asking_is_not_being_approved(self, authenticated_client, user, pending_status):
        """The row exists; the answer is what counts.

        The obvious bug is a policy that checks whether a request exists rather
        than what it says, which would make the form itself the gate — anyone
        could type two sentences and let themselves in.
        """
        CreatorValidation.objects.create(
            user=user, who="Someone", intent="Something", status=pending_status
        )

        response = authenticated_client.post(
            "/api/v1/collections/", {"headline": "Mercadillo", "mode": "COMMUNITY"}, format="json"
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
class TestWhatWasAlreadyThere:
    def test_an_existing_community_collection_stays_editable(
        self, authenticated_client, collection
    ):
        """Approval can be withdrawn; what somebody already runs must not freeze.

        The server only judges a *change* of mode (upstream's rule), and this
        deployment inherits it: an owner whose validation lapsed can still fix a
        typo on the group they are running.
        """
        collection.mode = Collection.Mode.COMMUNITY
        collection.save(update_fields=["mode"])

        response = authenticated_client.patch(
            f"/api/v1/collections/{collection.code}/",
            {"headline": "Renamed", "mode": "COMMUNITY"},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        collection.refresh_from_db()
        assert collection.headline == "Renamed"


@pytest.mark.django_db
class TestTheAdvertisedListIsTheAcceptedList:
    """One `capabilities()` call feeds both endpoints; hold them to it."""

    @pytest.mark.parametrize("approved", [False, True])
    def test_everything_advertised_is_accepted(self, authenticated_client, user, approved):
        if approved:
            approve(user)

        advertised = authenticated_client.get("/api/v1/auth/me/").data["capabilities"]

        for index, thing_type in enumerate(advertised["thing_types"]):
            response = authenticated_client.post(
                "/api/v1/things/",
                {"type": thing_type, "headline": f"Thing {index}", "thumbnail": "img/x"},
                format="json",
            )
            assert response.status_code == status.HTTP_201_CREATED, thing_type

    @pytest.mark.parametrize("approved", [False, True])
    def test_nothing_withheld_slips_through(self, authenticated_client, user, approved):
        if approved:
            approve(user)

        advertised = authenticated_client.get("/api/v1/auth/me/").data["capabilities"]
        withheld = set(Thing.Type.values) - set(advertised["thing_types"])

        for thing_type in withheld:
            response = authenticated_client.post(
                "/api/v1/things/",
                {"type": thing_type, "headline": "Withheld", "thumbnail": "img/x"},
                format="json",
            )
            assert response.status_code == status.HTTP_403_FORBIDDEN, thing_type


@pytest.mark.django_db
class TestThePolicyItself:
    def test_an_anonymous_caller_gets_the_open_half_without_a_query(
        self, django_assert_num_queries
    ):
        """`/collections/{code}` is public, and public pages must not query for
        a validation row that cannot exist."""
        from django.contrib.auth.models import AnonymousUser

        with django_assert_num_queries(0):
            capabilities = HostedCreatorPolicy().capabilities(AnonymousUser())

        assert capabilities.collection_modes == ("PROPRIETARY",)

    def test_the_lookup_happens_once_per_request(self, django_assert_num_queries, user):
        """Three `capabilities()` calls, one query.

        A create asks `allows_*` and then reads `request_url` off a second call;
        without the per-user memo that is a second and third round trip on every
        refusal, on the hot path of the two endpoints people use most.
        """
        policy = HostedCreatorPolicy()

        with django_assert_num_queries(1):
            policy.capabilities(user)
            policy.capabilities(user)
            policy.allows_thing_type(user, Thing.Type.LEND_THING)

    def test_the_request_url_resolves_to_the_form_that_exists(self, api_client):
        """Not a hard-coded string: the link and the route move together."""
        assert api_client.get(request_access_url()).status_code == status.HTTP_200_OK

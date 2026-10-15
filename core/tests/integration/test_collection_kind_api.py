"""The collections API speaks ``kind``: created with one, never changed, and gated by policy.

A kind says which verbs a collection holds (a stall gives or sells, a library lends
or rents, a shed books), so the verb list stored beside it is derived and checked
against the kind rather than trusted: PROPRIETARY always takes both verbs, a
COMMUNITY stall or library may switch prices off (free verb only) but never allow
only prices, and a shed is always PROPRIETARY with RESERVE alone.
"""

import pytest
from rest_framework import status

from core.models import Collection, Thing
from core.services.creator_policy import Capabilities
from core.tests.factories import also_in
from core.tests.sample_creator_policy import REQUEST_URL

URL = "/api/v1/collections/"
RESTRICTED = "core.tests.sample_creator_policy.RestrictedCreatorPolicy"
GIFT, SELL, LEND, RENT, RESERVE = (
    "GIFT_THING",
    "SELL_THING",
    "LEND_THING",
    "RENT_THING",
    "RESERVE_THING",
)


def _create(client, **body):
    return client.post(URL, {"headline": "Group", **body}, format="json")


@pytest.mark.django_db
class TestCreatingByKind:
    @pytest.mark.parametrize(
        "kind,verbs",
        [("STALL", [GIFT, SELL]), ("LIBRARY", [LEND, RENT]), ("SHED", [RESERVE])],
    )
    def test_each_kind_is_stored_with_its_own_verbs(self, authenticated_client, kind, verbs):
        res = _create(authenticated_client, kind=kind)

        assert res.status_code == status.HTTP_201_CREATED, res.data
        assert res.data["kind"] == kind
        assert res.data["allowed_thing_types"] == verbs
        assert Collection.objects.get(code=res.data["code"]).kind == kind

    @pytest.mark.parametrize(
        "verbs,kind", [([LEND], "LIBRARY"), ([SELL, GIFT], "STALL"), ([RESERVE], "SHED")]
    )
    def test_a_client_that_names_no_kind_gets_the_one_its_verbs_belong_to(
        self, authenticated_client, verbs, kind
    ):
        res = _create(authenticated_client, allowed_thing_types=verbs)

        assert res.status_code == status.HTTP_201_CREATED, res.data
        assert res.data["kind"] == kind

    @pytest.mark.parametrize("verbs", [[], [GIFT, LEND], [RESERVE, SELL]])
    def test_no_kind_and_no_single_family_is_refused(self, authenticated_client, verbs):
        res = _create(authenticated_client, allowed_thing_types=verbs)

        assert res.status_code == status.HTTP_400_BAD_REQUEST
        assert "one kind of thing: stall, library or shed" in str(res.data)
        assert not Collection.objects.filter(headline="Group").exists()

    def test_a_verb_that_does_not_exist_is_named(self, authenticated_client):
        res = _create(authenticated_client, allowed_thing_types=[GIFT, "SWAP_THING"])

        assert res.status_code == status.HTTP_400_BAD_REQUEST
        assert "SWAP_THING" in str(res.data)

    def test_a_verb_of_another_kind_is_refused_even_with_a_kind(self, authenticated_client):
        res = _create(authenticated_client, kind="STALL", allowed_thing_types=[LEND])

        assert res.status_code == status.HTTP_400_BAD_REQUEST
        assert not Collection.objects.filter(headline="Group").exists()

    def test_a_proprietary_collection_is_forced_to_both_verbs(self, authenticated_client):
        res = _create(authenticated_client, kind="STALL", allowed_thing_types=[GIFT])

        assert res.data["allowed_thing_types"] == [GIFT, SELL]


@pytest.mark.django_db
class TestTheCommunitySwitch:
    @pytest.mark.parametrize(
        "kind,free,paid",
        [("STALL", GIFT, SELL), ("LIBRARY", LEND, RENT)],
    )
    def test_members_who_may_not_set_a_price_leave_only_the_free_verb(
        self, authenticated_client, kind, free, paid
    ):
        res = _create(authenticated_client, kind=kind, mode="COMMUNITY", allowed_thing_types=[free])

        assert res.status_code == status.HTTP_201_CREATED, res.data
        assert res.data["allowed_thing_types"] == [free]

    @pytest.mark.parametrize("listed", [[], [GIFT, SELL]])
    def test_an_empty_or_full_list_means_prices_are_allowed(self, authenticated_client, listed):
        res = _create(
            authenticated_client, kind="STALL", mode="COMMUNITY", allowed_thing_types=listed
        )

        assert res.data["allowed_thing_types"] == [GIFT, SELL]

    @pytest.mark.parametrize("kind,paid", [("STALL", SELL), ("LIBRARY", RENT)])
    def test_only_the_paid_verb_is_refused(self, authenticated_client, kind, paid):
        res = _create(authenticated_client, kind=kind, mode="COMMUNITY", allowed_thing_types=[paid])

        assert res.status_code == status.HTTP_400_BAD_REQUEST
        assert "can't take only prices" in str(res.data)

    def test_a_shed_is_never_a_community(self, authenticated_client):
        res = _create(authenticated_client, kind="SHED", mode="COMMUNITY")

        assert res.status_code == status.HTTP_400_BAD_REQUEST
        assert "community collection" in str(res.data)


@pytest.mark.django_db
class TestTheKindNeverChanges:
    def test_naming_a_different_kind_is_refused(self, authenticated_client, collection):
        res = authenticated_client.patch(
            f"{URL}{collection.code}/", {"kind": "SHED"}, format="json"
        )

        assert res.status_code == status.HTTP_400_BAD_REQUEST
        assert "kind can't change" in str(res.data)
        collection.refresh_from_db()
        assert collection.kind == "STALL"

    def test_naming_the_same_kind_is_harmless(self, authenticated_client, collection):
        res = authenticated_client.patch(
            f"{URL}{collection.code}/", {"kind": "STALL", "headline": "Renamed"}, format="json"
        )

        assert res.status_code == status.HTTP_200_OK, res.data
        collection.refresh_from_db()
        assert collection.headline == "Renamed"

    def test_switching_the_prices_off_with_a_priced_thing_inside_is_still_refused(
        self, authenticated_client, collection, user
    ):
        collection.mode = "COMMUNITY"
        collection.allowed_thing_types = [GIFT, SELL]
        collection.save()
        also_in(
            collection,
            Thing.objects.create(code="SELL01", owner=user, headline="Lamp", type=SELL),
        )

        res = authenticated_client.patch(
            f"{URL}{collection.code}/", {"allowed_thing_types": [GIFT]}, format="json"
        )

        assert res.status_code == status.HTTP_400_BAD_REQUEST
        assert "orphaned" in str(res.data)

    def test_a_stall_holding_a_lend_can_still_be_saved_from_the_edit_page(
        self, authenticated_client, collection, user
    ):
        # The edit page always sends the verb list; a thing of the other family is
        # tolerated, so it must not make every save a 400.
        also_in(
            collection,
            Thing.objects.create(code="LEND01", owner=user, headline="Drill", type=LEND),
        )

        res = authenticated_client.patch(
            f"{URL}{collection.code}/",
            {"headline": "Renamed", "allowed_thing_types": [GIFT, SELL]},
            format="json",
        )

        assert res.status_code == status.HTTP_200_OK, res.data
        collection.refresh_from_db()
        assert collection.headline == "Renamed"
        assert collection.things.get(code="LEND01").type == LEND

    def test_a_mixed_stall_with_no_sale_inside_can_switch_the_prices_off(
        self, authenticated_client, collection, user
    ):
        collection.mode = "COMMUNITY"
        collection.save()
        also_in(
            collection,
            Thing.objects.create(code="LEND02", owner=user, headline="Drill", type=LEND),
        )

        res = authenticated_client.patch(
            f"{URL}{collection.code}/", {"allowed_thing_types": [GIFT]}, format="json"
        )

        assert res.status_code == status.HTTP_200_OK, res.data
        assert res.data["allowed_thing_types"] == [GIFT]

    def test_the_switch_can_be_flipped_when_nothing_is_priced(
        self, authenticated_client, collection
    ):
        collection.mode = "COMMUNITY"
        collection.save()

        res = authenticated_client.patch(
            f"{URL}{collection.code}/", {"allowed_thing_types": [GIFT]}, format="json"
        )

        assert res.status_code == status.HTTP_200_OK, res.data
        assert res.data["allowed_thing_types"] == [GIFT]

    def test_becoming_proprietary_widens_a_free_only_list(self, authenticated_client, collection):
        collection.mode = "COMMUNITY"
        collection.allowed_thing_types = [GIFT]
        collection.save()

        res = authenticated_client.patch(
            f"{URL}{collection.code}/", {"mode": "PROPRIETARY"}, format="json"
        )

        assert res.status_code == status.HTTP_200_OK, res.data
        assert res.data["allowed_thing_types"] == [GIFT, SELL]

    def test_a_shed_still_cannot_become_a_community(self, authenticated_client, user):
        shed = Collection.objects.create(
            code="SHED01",
            owner=user,
            headline="Shed",
            kind="SHED",
            allowed_thing_types=[RESERVE],
        )

        res = authenticated_client.patch(f"{URL}{shed.code}/", {"mode": "COMMUNITY"}, format="json")

        assert res.status_code == status.HTTP_400_BAD_REQUEST
        assert "can't become a community" in str(res.data)


@pytest.mark.django_db
class TestReadingTheKind:
    def test_detail_and_list_carry_it(self, authenticated_client, user):
        library = Collection.objects.create(
            code="LIBR01",
            owner=user,
            headline="L",
            kind="LIBRARY",
            allowed_thing_types=[LEND, RENT],
        )

        detail = authenticated_client.get(f"{URL}{library.code}/")
        listing = authenticated_client.get(URL)

        assert detail.data["kind"] == "LIBRARY"
        rows = listing.data["results"] if "results" in listing.data else listing.data
        assert [r["kind"] for r in rows if r["code"] == "LIBR01"] == ["LIBRARY"]


@pytest.mark.django_db
class TestThePolicyGatesKinds:
    @pytest.fixture(autouse=True)
    def _narrowed(self, settings):
        settings.CREATOR_POLICY = RESTRICTED  # gives GIFT and SELL, so only a stall

    def test_a_stall_is_open(self, authenticated_client):
        assert _create(authenticated_client, kind="STALL").status_code == status.HTTP_201_CREATED

    @pytest.mark.parametrize("kind", ["LIBRARY", "SHED"])
    def test_the_kinds_whose_verbs_are_withheld_are_refused_with_where_to_ask(
        self, authenticated_client, kind
    ):
        res = _create(authenticated_client, kind=kind)

        assert res.status_code == status.HTTP_403_FORBIDDEN
        assert kind.lower() in str(res.data)
        assert REQUEST_URL in str(res.data)
        assert not Collection.objects.filter(headline="Group").exists()

    def test_me_serves_the_kinds_the_policy_leaves_open(self, authenticated_client):
        caps = authenticated_client.get("/api/v1/auth/me/").data["capabilities"]

        assert caps["collection_kinds"] == ["STALL"]
        assert caps["thing_types"] == [GIFT, SELL]

    def test_the_standalone_offers_all_three(self, authenticated_client, settings):
        settings.CREATOR_POLICY = "core.services.creator_policy.OpenCreatorPolicy"

        caps = authenticated_client.get("/api/v1/auth/me/").data["capabilities"]

        assert caps["collection_kinds"] == ["STALL", "LIBRARY", "SHED"]


class TestKindsAreDerivedFromVerbs:
    @pytest.mark.parametrize(
        "verbs,kinds",
        [
            ((RENT,), ("LIBRARY",)),
            ((GIFT, RESERVE), ("STALL", "SHED")),
            ((), ()),
        ],
    )
    def test_one_verb_is_enough_to_open_its_kind(self, verbs, kinds):
        caps = Capabilities(collection_modes=("PROPRIETARY",), thing_types=verbs)

        assert caps.collection_kinds == kinds
        assert caps.as_dict()["collection_kinds"] == list(kinds)

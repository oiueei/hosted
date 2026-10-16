"""A thing's verb follows the price: the collection's kind and the fee give it.

In a stall a price makes a sale and no price a gift; in a library a price makes a
rental and no price a loan; a shed always books. The server decides, so an edit
that adds or drops a price moves the verb with it, and a client that names a verb
its price contradicts is told so rather than silently corrected.
"""

import pytest
from rest_framework import status

from core.models import Collection, Thing
from core.models.collection import derive_thing_type

THINGS = "/api/v1/things/"
BULK = "/api/v1/collections/{code}/things/bulk/"
GIFT, SELL, LEND, RENT, RESERVE = (
    "GIFT_THING",
    "SELL_THING",
    "LEND_THING",
    "RENT_THING",
    "RESERVE_THING",
)


def _group(owner, kind, code="GRP001", **fields):
    return Collection.objects.create(code=code, owner=owner, headline="G", kind=kind, **fields)


def _create(client, group, **body):
    return client.post(
        THINGS, {"headline": "A thing", "collection_code": group.code, **body}, format="json"
    )


class TestDerivation:
    @pytest.mark.parametrize(
        "kind,fee,expected",
        [
            ("STALL", None, GIFT),
            ("STALL", 0, GIFT),
            ("STALL", 5, SELL),
            ("LIBRARY", None, LEND),
            ("LIBRARY", 0, LEND),
            ("LIBRARY", 5, RENT),
            ("SHED", None, RESERVE),
            ("SHED", 5, RESERVE),
        ],
    )
    def test_the_four_cases_and_the_shed(self, kind, fee, expected):
        assert derive_thing_type(kind, fee) == expected


@pytest.mark.django_db
class TestCreating:
    @pytest.mark.parametrize(
        "kind,body,expected",
        [
            ("STALL", {}, GIFT),
            ("STALL", {"fee": "0"}, GIFT),
            ("STALL", {"fee": "4.50"}, SELL),
            ("LIBRARY", {}, LEND),
            ("LIBRARY", {"fee": "4.50"}, RENT),
            ("SHED", {}, RESERVE),
        ],
    )
    def test_the_server_puts_the_verb(self, authenticated_client, user, kind, body, expected):
        res = _create(authenticated_client, _group(user, kind), **body)

        assert res.status_code == status.HTTP_201_CREATED, res.data
        assert Thing.objects.get(code=res.data["code"]).type == expected

    def test_a_verb_that_agrees_with_the_price_is_accepted(self, authenticated_client, user):
        res = _create(authenticated_client, _group(user, "STALL"), type=SELL, fee="3.00")

        assert res.status_code == status.HTTP_201_CREATED, res.data

    @pytest.mark.parametrize(
        "kind,body,phrase",
        [
            ("STALL", {"type": SELL}, "with a price it's a sale, without one a gift"),
            ("STALL", {"type": GIFT, "fee": "3.00"}, "with a price it's a sale"),
            ("LIBRARY", {"type": LEND, "fee": "3.00"}, "with a price it's a rental"),
            ("LIBRARY", {"type": RENT}, "without one a loan"),
            ("SHED", {"type": GIFT}, "always a reservation"),
        ],
    )
    def test_a_contradicting_verb_is_a_400_that_says_why(
        self, authenticated_client, user, kind, body, phrase
    ):
        res = _create(authenticated_client, _group(user, kind), **body)

        assert res.status_code == status.HTTP_400_BAD_REQUEST
        assert phrase in str(res.data["type"])
        assert not Thing.objects.filter(headline="A thing").exists()

    def test_a_loan_can_carry_a_deposit_without_naming_its_verb(self, authenticated_client, user):
        res = _create(authenticated_client, _group(user, "LIBRARY"), deposit="20.00")

        assert res.status_code == status.HTTP_201_CREATED, res.data
        assert Thing.objects.get(code=res.data["code"]).deposit is not None

    def test_a_gift_still_cannot_carry_a_deposit(self, authenticated_client, user):
        res = _create(authenticated_client, _group(user, "STALL"), deposit="20.00")

        assert res.status_code == status.HTTP_400_BAD_REQUEST
        assert "deposit" in str(res.data)

    def test_a_thing_with_no_collection_keeps_the_old_rules(self, authenticated_client):
        res = authenticated_client.post(
            THINGS, {"headline": "Loose", "type": SELL, "fee": "3.00"}, format="json"
        )

        assert res.status_code == status.HTTP_201_CREATED, res.data
        assert Thing.objects.get(code=res.data["code"]).type == SELL

    def test_a_collection_that_is_not_theirs_is_not_answered_for(self, authenticated_client2, user):
        """A stranger told 'in a stall…' would learn the kind of a private group."""
        group = _group(user, "STALL", visibility=Collection.Visibility.PRIVATE)

        res = _create(authenticated_client2, group, type=LEND)

        assert res.status_code == status.HTTP_403_FORBIDDEN
        assert "stall" not in str(res.data)


@pytest.mark.django_db
class TestACommunityThatTakesNoPrices:
    @pytest.fixture
    def free_group(self, user, user2):
        group = _group(user, "STALL", mode=Collection.Mode.COMMUNITY, allowed_thing_types=[GIFT])
        group.invites.add(user2)
        return group

    def test_a_price_is_refused_with_its_own_message(self, authenticated_client2, free_group):
        res = _create(authenticated_client2, free_group, fee="3.00")

        assert res.status_code == status.HTTP_400_BAD_REQUEST
        assert "This group doesn't take prices." in str(res.data)
        assert res.data["code"] == "no_prices_here"

    def test_without_a_price_a_member_gives_freely(self, authenticated_client2, free_group):
        res = _create(authenticated_client2, free_group)

        assert res.status_code == status.HTTP_201_CREATED, res.data


@pytest.mark.django_db
class TestEditing:
    def _thing(self, owner, group, thing_type, **fields):
        thing = Thing.objects.create(
            code="EDT001", owner=owner, headline="T", type=thing_type, **fields
        )
        group.things.add(thing)
        return thing

    @pytest.mark.parametrize(
        "kind,start,fee,expected",
        [
            ("STALL", GIFT, "5.00", SELL),
            ("STALL", SELL, None, GIFT),
            ("LIBRARY", LEND, "5.00", RENT),
            ("LIBRARY", RENT, None, LEND),
        ],
    )
    def test_setting_or_dropping_the_price_moves_the_verb(
        self, authenticated_client, user, kind, start, fee, expected
    ):
        thing = self._thing(
            user, _group(user, kind), start, fee=5 if start in (SELL, RENT) else None
        )

        res = authenticated_client.patch(f"{THINGS}{thing.code}/", {"fee": fee}, format="json")

        assert res.status_code == status.HTTP_200_OK, res.data
        thing.refresh_from_db()
        assert thing.type == expected

    def test_an_edit_that_touches_neither_price_nor_verb_leaves_the_verb(
        self, authenticated_client, user
    ):
        thing = self._thing(user, _group(user, "STALL"), SELL, fee=5)

        res = authenticated_client.patch(
            f"{THINGS}{thing.code}/", {"headline": "New"}, format="json"
        )

        assert res.status_code == status.HTTP_200_OK, res.data
        thing.refresh_from_db()
        assert thing.type == SELL

    def test_a_legacy_gift_with_a_fee_keeps_its_verb_until_its_price_is_edited(
        self, authenticated_client, user
    ):
        """Things made before verbs followed prices may disagree with their price;
        an edit that touches neither one must not rewrite them behind the owner."""
        thing = self._thing(user, _group(user, "STALL"), GIFT, fee=5)

        res = authenticated_client.patch(
            f"{THINGS}{thing.code}/", {"headline": "New"}, format="json"
        )

        assert res.status_code == status.HTTP_200_OK, res.data
        thing.refresh_from_db()
        assert thing.type == GIFT

    def test_naming_a_verb_the_price_contradicts_is_a_400(self, authenticated_client, user):
        thing = self._thing(user, _group(user, "STALL"), GIFT)

        res = authenticated_client.patch(
            f"{THINGS}{thing.code}/", {"type": SELL, "fee": None}, format="json"
        )

        assert res.status_code == status.HTTP_400_BAD_REQUEST
        assert "the verb follows the price" in str(res.data)

    def test_a_loan_a_mixed_collection_kept_is_not_turned_into_a_gift(
        self, authenticated_client, user
    ):
        """The migration leaves the minority family's things with their verb."""
        thing = self._thing(user, _group(user, "STALL"), LEND)

        res = authenticated_client.patch(f"{THINGS}{thing.code}/", {"fee": "5.00"}, format="json")

        assert res.status_code == status.HTTP_200_OK, res.data
        thing.refresh_from_db()
        assert thing.type == LEND

    def test_a_community_group_without_prices_refuses_one_on_edit(self, authenticated_client, user):
        group = _group(user, "STALL", mode=Collection.Mode.COMMUNITY, allowed_thing_types=[GIFT])
        thing = self._thing(user, group, GIFT)

        res = authenticated_client.patch(f"{THINGS}{thing.code}/", {"fee": "5.00"}, format="json")

        assert res.status_code == status.HTTP_400_BAD_REQUEST
        assert "This group doesn't take prices." in str(res.data)


@pytest.mark.django_db
class TestCsvImport:
    def test_the_type_column_is_optional(self, authenticated_client, user):
        group = _group(user, "LIBRARY")

        res = authenticated_client.post(
            BULK.format(code=group.code),
            {"rows": [{"headline": "Ladder"}, {"headline": "Drill", "fee": "4"}]},
            format="json",
        )

        assert res.status_code == status.HTTP_201_CREATED, res.data
        types = dict(group.things.values_list("headline", "type"))
        assert types == {"Ladder": LEND, "Drill": RENT}

    def test_a_row_whose_verb_contradicts_its_price_names_the_row(self, authenticated_client, user):
        group = _group(user, "STALL")

        res = authenticated_client.post(
            BULK.format(code=group.code),
            {"rows": [{"headline": "Fine"}, {"headline": "Odd", "type": SELL}]},
            format="json",
        )

        assert res.status_code == status.HTTP_400_BAD_REQUEST
        assert [e["row"] for e in res.data["errors"]] == [1]
        assert "the verb follows the price" in str(res.data["errors"][0]["errors"]["type"])
        assert not group.things.exists()

    def test_a_deposit_on_a_priced_loan_row_is_fine_and_on_a_gift_row_is_not(
        self, authenticated_client, user
    ):
        library = _group(user, "LIBRARY", code="LIBR02")
        stall = _group(user, "STALL", code="STAL02")

        ok = authenticated_client.post(
            BULK.format(code=library.code),
            {"rows": [{"headline": "Drill", "fee": "4", "deposit": "20"}]},
            format="json",
        )
        bad = authenticated_client.post(
            BULK.format(code=stall.code),
            {"rows": [{"headline": "Vase", "deposit": "20"}]},
            format="json",
        )

        assert ok.status_code == status.HTTP_201_CREATED, ok.data
        assert bad.status_code == status.HTTP_400_BAD_REQUEST
        assert "deposit" in str(bad.data)

"""
Deposits: a number the owner asks to be left, and the words that say when it
comes back.

The rule worth protecting is that **a deposit only exists where something is
returned**. `fee` has no such rule — a price on a gift is merely odd — so there
was no precedent to copy, and the negative tests here are the rule itself. They
are written against the serializers rather than the endpoints because the JSON
API, the edit form and the CSV import are three doors into one column, and each
one gets checked below.

`deposit_policy` is owner prose like every other, so it carries the repo's
classic trap with it: the visible limit is **per language** and the column is
wider than it. Both halves are pinned.
"""

import json

import pytest

from core.models import Collection, Thing
from core.serializers import (
    CollectionCreateSerializer,
    CollectionSerializer,
    CollectionUpdateSerializer,
    ThingCreateSerializer,
    ThingSerializer,
    ThingUpdateSerializer,
)
from core.serializers.thing import ThingBulkRowSerializer
from core.utils import parse_localized

pytestmark = pytest.mark.django_db


def _thing(**kwargs):
    data = {"type": Thing.Type.LEND_THING, "headline": "A drill"}
    data.update(kwargs)
    return data


class TestWhoMayAskForADeposit:
    @pytest.mark.parametrize("thing_type", ["LEND_THING", "RENT_THING"])
    def test_a_loan_and_a_rental_may(self, thing_type):
        serializer = ThingCreateSerializer(data=_thing(type=thing_type, deposit="50.00"))

        assert serializer.is_valid(), serializer.errors
        assert str(serializer.validated_data["deposit"]) == "50.00"

    @pytest.mark.parametrize("thing_type", ["GIFT_THING", "SELL_THING"])
    def test_a_gift_and_a_sale_may_not(self, thing_type):
        # Nothing comes back, so there is nothing to leave against it.
        serializer = ThingCreateSerializer(data=_thing(type=thing_type, deposit="50.00"))

        assert not serializer.is_valid()
        assert "deposit" in serializer.errors

    @pytest.mark.parametrize("thing_type", ["GIFT_THING", "SELL_THING"])
    def test_a_gift_and_a_sale_are_fine_without_one(self, thing_type):
        assert ThingCreateSerializer(data=_thing(type=thing_type)).is_valid()

    def test_a_price_is_not_a_deposit_and_keeps_its_freedom(self):
        # `fee` deliberately has no type rule; adding one here would be a
        # behaviour change smuggled in beside a new field.
        assert ThingCreateSerializer(data=_thing(type="GIFT_THING", fee="10.00")).is_valid()

    def test_a_rental_may_carry_both_and_they_are_two_numbers(self, user):
        serializer = ThingCreateSerializer(
            data=_thing(type="RENT_THING", fee="10.00", deposit="50.00")
        )
        assert serializer.is_valid(), serializer.errors

        thing = serializer.save(owner=user)
        read = ThingSerializer(thing, context={"request": None}).data
        assert read["fee"] == "10.00"
        assert read["deposit"] == "50.00"

    def test_a_negative_deposit_is_not_a_deposit(self):
        assert not ThingCreateSerializer(data=_thing(deposit="-1.00")).is_valid()


class TestChangingTheTypeOfAThingThatCarriesOne:
    """The rule is about the row that lands, not about the payload: an edit that
    only mentions the type still has to answer for the amount already there."""

    def test_turning_a_loan_with_a_deposit_into_a_gift_is_refused(self, user):
        thing = Thing.objects.create(
            code="LEND01",
            owner=user,
            headline="A drill",
            type=Thing.Type.LEND_THING,
            deposit="50.00",
        )

        serializer = ThingUpdateSerializer(thing, data={"type": "GIFT_THING"}, partial=True)

        assert not serializer.is_valid()
        assert "deposit" in serializer.errors

    def test_clearing_the_amount_in_the_same_breath_is_allowed(self, user):
        thing = Thing.objects.create(
            code="LEND02",
            owner=user,
            headline="A drill",
            type=Thing.Type.LEND_THING,
            deposit="50.00",
        )

        serializer = ThingUpdateSerializer(
            thing, data={"type": "GIFT_THING", "deposit": None}, partial=True
        )

        assert serializer.is_valid(), serializer.errors
        assert serializer.save().deposit is None

    def test_editing_something_else_entirely_does_not_trip_over_it(self, user):
        thing = Thing.objects.create(
            code="LEND03",
            owner=user,
            headline="A drill",
            type=Thing.Type.LEND_THING,
            deposit="50.00",
        )

        serializer = ThingUpdateSerializer(thing, data={"headline": "A better drill"}, partial=True)

        assert serializer.is_valid(), serializer.errors


class TestTheCsvDoor:
    def test_a_spreadsheet_decimal_comma_is_understood(self):
        # The one input path with no NumberInput in front of it (S9), so it
        # takes what a Spanish or Catalan spreadsheet actually exports.
        serializer = ThingBulkRowSerializer(
            data={"type": "RENT_THING", "headline": "A tent", "deposit": "50,00"}
        )

        assert serializer.is_valid(), serializer.errors
        assert str(serializer.validated_data["deposit"]) == "50.00"

    def test_a_number_that_could_mean_two_things_is_refused_not_guessed(self):
        serializer = ThingBulkRowSerializer(
            data={"type": "RENT_THING", "headline": "A tent", "deposit": "1.234,56"}
        )

        assert not serializer.is_valid()
        assert "deposit" in serializer.errors

    def test_the_type_rule_reaches_the_csv_too(self):
        serializer = ThingBulkRowSerializer(
            data={"type": "GIFT_THING", "headline": "A tent", "deposit": "50,00"}
        )

        assert not serializer.is_valid()
        assert "deposit" in serializer.errors


class TestTheGroupsPolicy:
    POLICY = "50 €, back when the drill comes home in one piece."

    def test_a_group_can_say_how_deposits_work_in_it(self, user):
        serializer = CollectionCreateSerializer(
            data={"headline": "Tools", "deposit_policy": self.POLICY}
        )
        assert serializer.is_valid(), serializer.errors

        collection = serializer.save(owner=user)
        assert CollectionSerializer(collection).data["deposit_policy"] == self.POLICY

    def test_saying_nothing_is_the_off_switch_and_costs_no_data(self, user, collection):
        # No boolean to keep in step with the text: an empty policy IS "no
        # deposits here".
        assert collection.deposit_policy == ""
        assert CollectionSerializer(collection).data["deposit_policy"] == ""

    def test_a_bilingual_group_says_it_twice_and_both_survive(self, user, collection):
        policy = {"es": "50 €, se devuelven al volver", "ca": "50 €, es tornen en tornar"}

        serializer = CollectionUpdateSerializer(
            collection, data={"deposit_policy": json.dumps(policy)}, partial=True
        )
        assert serializer.is_valid(), serializer.errors
        saved = serializer.save()

        # Stored as the map the owner wrote — resolving it here would pick one
        # language for everybody.
        assert parse_localized(saved.deposit_policy) == policy

    def test_the_visible_limit_is_per_language(self, user, collection):
        too_long = json.dumps({"es": "x" * 257})

        serializer = CollectionUpdateSerializer(
            collection, data={"deposit_policy": too_long}, partial=True
        )

        assert not serializer.is_valid()
        assert "deposit_policy" in serializer.errors

    def test_and_three_full_languages_still_fit_the_column(self, user, collection):
        # The repo's classic trap: 256 is what one language may say, and the
        # column is 1024 so that all three plus the JSON scaffolding fit.
        full = json.dumps({lang: "x" * 256 for lang in ("es", "ca", "en")})
        assert len(full) > Collection._meta.get_field("deposit_policy").max_length - 256

        serializer = CollectionUpdateSerializer(
            collection, data={"deposit_policy": full}, partial=True
        )

        assert serializer.is_valid(), serializer.errors
        saved = serializer.save()
        assert len(saved.deposit_policy) <= Collection._meta.get_field("deposit_policy").max_length

    def test_html_in_a_policy_is_refused_like_any_other_owner_text(self, user, collection):
        serializer = CollectionUpdateSerializer(
            collection, data={"deposit_policy": "<script>alert(1)</script>"}, partial=True
        )

        assert not serializer.is_valid()

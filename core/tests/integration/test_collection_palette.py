"""A collection carries its own palette (theeeme + koro), and the API says so.

The palette moved from the reader to the group: a group's pages wear the colours
its curators chose, for anyone who can read the page — a visitor with no session
included, since they are colours — and the twelve rows of `theeemes` are the only
palettes a curator can pick. The app's own palette is a different table and is
never reachable from here.
"""

import pytest
from rest_framework import status

from core.models import Collection, Theeeme, Thing

JMPA = {
    "color_01": "metro",
    "color_02": "gold",
    "color_03": "tram",
    "color_04": "black",
    "color_05": "white",
    "color_06": "",
}


@pytest.fixture
def jmpa_group(public_collection):
    """A public group wearing the JMPA01 palette and the wave koro."""
    public_collection.theeeme_id = "JMPA01"
    public_collection.koro = "wave"
    public_collection.save()
    return public_collection


@pytest.mark.django_db
class TestTheCollectionRead:
    def test_an_anonymous_reader_gets_the_groups_colours_and_koro(self, api_client, jmpa_group):
        response = api_client.get(f"/api/v1/collections/{jmpa_group.code}/")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["theeeme"] == "JMPA01"
        assert response.data["koro"] == "wave"
        assert response.data["theeeme_colors"] == JMPA

    def test_two_groups_wear_their_own_palettes(self, api_client, jmpa_group, user):
        other = Collection.objects.create(
            code="OTHER1",
            owner=user,
            headline="Other",
            visibility=Collection.Visibility.PUBLIC,
            theeeme_id="BUU331",
            koro="pulse",
        )

        a = api_client.get(f"/api/v1/collections/{jmpa_group.code}/").data
        b = api_client.get(f"/api/v1/collections/{other.code}/").data

        assert a["theeeme_colors"]["color_01"] == "metro"
        assert b["theeeme_colors"]["color_01"] == "bus"
        assert (a["koro"], b["koro"]) == ("wave", "pulse")

    def test_reading_the_palette_costs_no_extra_query(
        self, api_client, jmpa_group, django_assert_max_num_queries
    ):
        # The palette is joined with the collection, not fetched on its own.
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        with CaptureQueriesContext(connection) as queries:
            api_client.get(f"/api/v1/collections/{jmpa_group.code}/")

        assert [
            q for q in queries if 'FROM "theeemes"' in q["sql"] and "JOIN" not in q["sql"]
        ] == []


@pytest.mark.django_db
class TestCreatingAndEditing:
    BODY = {"headline": "Palette group", "kind": "STALL"}

    def test_a_curator_picks_a_palette_and_a_koro_when_creating(self, authenticated_client):
        response = authenticated_client.post(
            "/api/v1/collections/",
            {**self.BODY, "theeeme": "JMPA01", "koro": "calm"},
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        group = Collection.objects.get(code=response.data["code"])
        assert (group.theeeme_id, group.koro) == ("JMPA01", "calm")

    def test_left_out_a_new_group_gets_an_existing_palette_and_the_basic_koro(
        self, authenticated_client
    ):
        response = authenticated_client.post("/api/v1/collections/", self.BODY, format="json")

        assert response.status_code == status.HTTP_201_CREATED
        group = Collection.objects.get(code=response.data["code"])
        assert Theeeme.objects.filter(code=group.theeeme_id).exists()
        assert group.koro == "basic"

    @pytest.mark.parametrize("field, value", [("theeeme", "NOPE99"), ("koro", "tsunami")])
    def test_an_unknown_palette_or_koro_is_refused(self, authenticated_client, field, value):
        response = authenticated_client.post(
            "/api/v1/collections/", {**self.BODY, field: value}, format="json"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert field in response.data

    def test_the_apps_own_palette_cannot_be_named(self, authenticated_client):
        """`Braaanding` is not a row of `theeemes`, so its code is not a palette."""
        response = authenticated_client.post(
            "/api/v1/collections/", {**self.BODY, "theeeme": "OIUEEI"}, format="json"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "theeeme" in response.data

    def test_a_curator_changes_both_and_an_update_without_them_keeps_them(
        self, authenticated_client, jmpa_group
    ):
        url = f"/api/v1/collections/{jmpa_group.code}/"

        kept = authenticated_client.patch(url, {"headline": "Renamed"}, format="json")
        assert kept.status_code == status.HTTP_200_OK
        jmpa_group.refresh_from_db()
        assert (jmpa_group.theeeme_id, jmpa_group.koro) == ("JMPA01", "wave")

        changed = authenticated_client.patch(
            url, {"theeeme": "BUU331", "koro": "beat"}, format="json"
        )
        assert changed.status_code == status.HTTP_200_OK
        jmpa_group.refresh_from_db()
        assert (jmpa_group.theeeme_id, jmpa_group.koro) == ("BUU331", "beat")

    def test_a_member_cannot_repaint_the_group(self, authenticated_client2, jmpa_group, user2):
        jmpa_group.invites.add(user2)

        response = authenticated_client2.patch(
            f"/api/v1/collections/{jmpa_group.code}/", {"koro": "beat"}, format="json"
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        jmpa_group.refresh_from_db()
        assert jmpa_group.koro == "wave"


@pytest.mark.django_db
class TestTheSelectorStaysTheTwelve:
    def test_the_list_holds_only_rows_of_the_theeemes_table(self, authenticated_client):
        response = authenticated_client.get("/api/v1/theeemes/")

        assert response.status_code == status.HTTP_200_OK
        rows = response.data["results"] if "results" in response.data else response.data
        codes = {row["code"] for row in rows}
        assert codes == set(Theeeme.objects.values_list("code", flat=True))
        assert "OIUEEI" not in codes


@pytest.mark.django_db
class TestTheThingCarriesItsGroupsPalette:
    def _thing_in(self, group, owner):
        thing = Thing.objects.create(code="PALTH1", type="GIFT_THING", owner=owner, headline="T")
        group.things.add(thing)
        return thing

    def test_a_thing_read_through_a_public_group_wears_that_groups_palette(
        self, api_client, jmpa_group, user
    ):
        thing = self._thing_in(jmpa_group, user)

        data = api_client.get(f"/api/v1/things/{thing.code}/").data

        assert data["collection_theeeme_colors"] == JMPA
        assert data["collection_koro"] == "wave"

    def test_a_thing_in_a_private_group_gives_a_stranger_no_palette(self, collection, user):
        """The same viewable-collection rule as `collection_language`: a reader who
        cannot read the group is told nothing of it, colours included. Asked of the
        serializer directly, because the endpoint may refuse the thing altogether."""
        from rest_framework.request import Request
        from rest_framework.test import APIRequestFactory

        from core.serializers import ThingSerializer

        collection.visibility = Collection.Visibility.PRIVATE
        collection.theeeme_id = "JMPA01"
        collection.koro = "wave"
        collection.save()
        thing = self._thing_in(collection, user)
        request = Request(APIRequestFactory().get("/"))

        data = ThingSerializer(thing, context={"request": request}).data

        assert data["collection_theeeme_colors"] is None
        assert data["collection_koro"] == ""


@pytest.mark.django_db
class TestTheSharePreview:
    def test_the_door_of_a_group_carries_its_palette(self, api_client, collection):
        collection.theeeme_id = "JMPA01"
        collection.koro = "vibration"
        collection.share_token = "tokentokentokentokento1"
        collection.save()

        data = api_client.get("/api/v1/share/tokentokentokentokento1/preview/").data

        assert data["theeeme_colors"] == JMPA
        assert data["koro"] == "vibration"


@pytest.mark.django_db
class TestTheExports:
    def test_the_collection_export_carries_the_palette(self, authenticated_client, jmpa_group):
        from core.services.export_service import build_collection_export

        payload = build_collection_export(jmpa_group)

        assert payload["collection"]["theeeme"]["code"] == "JMPA01"
        assert payload["collection"]["koro"] == "wave"

    def test_the_account_export_names_no_palette(self, user, jmpa_group):
        from core.services.export_service import build_account_export

        payload = build_account_export(user)

        assert not {"theeeme", "koro"} & set(payload["profile"])
        for owned in payload["collections_owned"]:
            assert not {"theeeme", "koro"} & set(owned)

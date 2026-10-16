"""DailyActivityMiddleware's per-device counts — numbers only, nobody in them."""

from datetime import date
from unittest.mock import patch

import pytest
import time_machine
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from core.models import DailyActivity, DeviceDay

PHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148"
DESKTOP = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0.0.0 Safari/537.36"
)


def client_for(user, user_agent):
    client = APIClient()
    client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}",
        HTTP_USER_AGENT=user_agent,
    )
    return client


def count(device, metric, day=None):
    qs = DeviceDay.objects.filter(device=device, metric=metric)
    if day:
        qs = qs.filter(date=day)
    row = qs.first()
    return row.count if row else 0


@pytest.mark.django_db
class TestPeopleCount:
    def test_one_person_on_a_phone_counts_once_a_day(self, user):
        phone = client_for(user, PHONE)
        phone.get("/api/v1/auth/me/")
        phone.get("/api/v1/auth/me/")
        assert count("MOBILE", "PEOPLE") == 1

    def test_the_same_person_on_a_laptop_counts_in_the_other_group_too(self, user):
        client_for(user, PHONE).get("/api/v1/auth/me/")
        client_for(user, PHONE).get("/api/v1/auth/me/")
        client_for(user, DESKTOP).get("/api/v1/auth/me/")
        assert count("OTHER", "PEOPLE") == 1
        assert count("MOBILE", "PEOPLE") == 1

    def test_another_person_on_a_phone_adds_one(self, user, user2):
        client_for(user, PHONE).get("/api/v1/auth/me/")
        client_for(user2, PHONE).get("/api/v1/auth/me/")
        assert count("MOBILE", "PEOPLE") == 2

    def test_the_next_day_starts_new_rows_with_their_own_date(self, user):
        with time_machine.travel("2026-10-19 10:00", tick=False):
            client_for(user, PHONE).get("/api/v1/auth/me/")
        with time_machine.travel("2026-10-20 10:00", tick=False):
            client_for(user, PHONE).get("/api/v1/auth/me/")
        assert count("MOBILE", "PEOPLE", date(2026, 10, 19)) == 1
        assert count("MOBILE", "PEOPLE", date(2026, 10, 20)) == 1

    def test_an_anonymous_request_counts_nothing(self, api_client):
        api_client.credentials(HTTP_USER_AGENT=PHONE)
        assert api_client.get("/api/v1/collections/").status_code == 401
        assert DeviceDay.objects.count() == 0

    def test_a_request_with_no_user_agent_counts_nothing(self, user):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
        client.get("/api/v1/auth/me/")
        assert DeviceDay.objects.count() == 0

    def test_daily_activity_keeps_one_row_per_person_and_day(self, user):
        client_for(user, PHONE).get("/api/v1/auth/me/")
        client_for(user, DESKTOP).get("/api/v1/auth/me/")
        assert DailyActivity.objects.filter(user=user).count() == 1


@pytest.mark.django_db
class TestFormSavesCount:
    def test_creating_a_collection_on_a_phone_counts_a_save(self, user):
        resp = client_for(user, PHONE).post(
            "/api/v1/collections/", {"headline": "Garden"}, format="json"
        )
        assert resp.status_code == 201
        assert count("MOBILE", "FORM_SAVES") == 1

    def test_editing_a_thing_on_a_desktop_counts_a_save(self, user, thing):
        resp = client_for(user, DESKTOP).patch(
            f"/api/v1/things/{thing.code}/", {"headline": "Renamed"}, format="json"
        )
        assert resp.status_code == 200
        assert count("OTHER", "FORM_SAVES") == 1
        assert count("MOBILE", "FORM_SAVES") == 0

    def test_editing_a_collection_counts_a_save(self, user, collection):
        resp = client_for(user, PHONE).patch(
            f"/api/v1/collections/{collection.code}/", {"headline": "Renamed"}, format="json"
        )
        assert resp.status_code == 200
        assert count("MOBILE", "FORM_SAVES") == 1

    def test_every_save_counts_none_is_deduplicated(self, user, thing):
        client = client_for(user, PHONE)
        for name in ("One", "Two", "Three"):
            client.patch(f"/api/v1/things/{thing.code}/", {"headline": name}, format="json")
        assert count("MOBILE", "FORM_SAVES") == 3

    def test_a_refused_save_counts_nothing(self, user):
        resp = client_for(user, PHONE).post("/api/v1/collections/", {}, format="json")
        assert resp.status_code == 400
        assert count("MOBILE", "FORM_SAVES") == 0

    def test_reading_a_collection_is_not_a_save(self, user, collection):
        client_for(user, PHONE).get(f"/api/v1/collections/{collection.code}/")
        assert count("MOBILE", "FORM_SAVES") == 0


@pytest.mark.django_db
class TestCountingNeverBreaksAnything:
    def test_a_failed_device_write_leaves_the_response_good(self, user):
        with patch("core.models.activity.DeviceDay.objects.get_or_create", side_effect=Exception):
            resp = client_for(user, PHONE).get("/api/v1/auth/me/")
        assert resp.status_code == 200

    def test_a_failed_device_write_does_not_lose_the_activity_row(self, user):
        with patch("core.models.activity.DeviceDay.objects.get_or_create", side_effect=Exception):
            client_for(user, PHONE).get("/api/v1/auth/me/")
        assert DailyActivity.objects.filter(user=user).count() == 1

    def test_no_row_holds_the_user_or_the_user_agent(self, user, thing):
        client = client_for(user, PHONE)
        client.get("/api/v1/auth/me/")
        client.patch(f"/api/v1/things/{thing.code}/", {"headline": "Renamed"}, format="json")
        rows = list(DeviceDay.objects.all())
        assert rows
        for row in rows:
            held = " ".join(str(getattr(row, f.name)) for f in row._meta.get_fields())
            assert user.code not in held.replace(row.code, "")
            assert user.email not in held
            assert "iPhone" not in held and "Mozilla" not in held

"""The two counters behind the request-access page — numbers only, nobody in them.

**Tests code that is not in the standalone.** What it protects: the page that
explains what opens on request can say how often each of its sections is read
(`SEEN`) and how often "Request access" is pressed from it (`ASKED`) without
keeping anything about the people doing it. A row is a day, a need, a metric and a
number. Whatever fails while counting never costs the reader their page or the
redirect to the form.
"""

from datetime import date
from unittest.mock import patch

import pytest
import time_machine
from django.contrib import admin
from django.db import IntegrityError, transaction
from django.test import RequestFactory, override_settings

from core.models import User
from hosted.admin import AccessInterestAdmin
from hosted.models import AccessInterest
from hosted.tally import REQUEST_ACCESS

SEEN_URL = "/api/v1/access/seen/"
NEEDS = ["library", "rent", "shed", "community"]
DAY = "2026-10-21 12:00"


def seen(client, need, **extra):
    return client.post(SEEN_URL, {"need": need}, format="json", **extra)


def count(need, metric, day=None):
    rows = AccessInterest.objects.filter(need=need, metric=metric)
    if day:
        rows = rows.filter(date=day)
    row = rows.first()
    return row.count if row else 0


@pytest.mark.django_db
class TestSeen:
    @pytest.mark.parametrize("need", NEEDS)
    def test_each_need_adds_to_its_own_row_and_day(self, api_client, need):
        with time_machine.travel(DAY, tick=False):
            response = seen(api_client, need)

        assert response.status_code == 204
        assert count(need, "SEEN", date(2026, 10, 21)) == 1
        assert AccessInterest.objects.exclude(need=need).count() == 0

    def test_it_counts_every_reading_and_a_new_day_starts_a_new_row(self, api_client):
        with time_machine.travel("2026-10-21 12:00", tick=False):
            seen(api_client, "rent")
            seen(api_client, "rent")
        with time_machine.travel("2026-10-22 12:00", tick=False):
            seen(api_client, "rent")

        assert count("rent", "SEEN", date(2026, 10, 21)) == 2
        assert count("rent", "SEEN", date(2026, 10, 22)) == 1

    @pytest.mark.parametrize("body", [{"need": "teleport"}, {"need": ""}, {}, {"need": 3}])
    def test_a_need_that_does_not_exist_is_a_400_and_writes_nothing(self, api_client, body):
        response = api_client.post(SEEN_URL, body, format="json")

        assert response.status_code == 400
        assert AccessInterest.objects.count() == 0

    def test_it_needs_no_session(self, api_client):
        assert seen(api_client, "shed").status_code == 204

    def test_a_failed_write_is_still_a_204_and_the_page_never_notices(self, api_client):
        with patch(
            "hosted.models.AccessInterest.objects.get_or_create", side_effect=Exception("db down")
        ):
            response = seen(api_client, "shed")

        assert response.status_code == 204

    @override_settings(
        RATELIMIT_ENABLE=True,
        CACHES={
            "default": {
                "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
                "LOCATION": "access-seen-ratelimit-test",
            }
        },
    )
    def test_thirty_a_minute_from_one_address_and_no_more(self, api_client):
        statuses = [seen(api_client, "rent").status_code for _ in range(31)]

        assert statuses[:30] == [204] * 30
        assert statuses[30] == 429
        assert count("rent", "SEEN") == 30


@pytest.mark.django_db
class TestAsked:
    @pytest.mark.parametrize("need", NEEDS)
    def test_a_valid_for_adds_one_and_still_goes_to_the_form(self, api_client, need):
        with time_machine.travel(DAY, tick=False):
            response = api_client.get(f"/request-access/?for={need}")

        assert response.status_code == 302
        assert response["Location"] == REQUEST_ACCESS["es"]
        assert count(need, "ASKED", date(2026, 10, 21)) == 1

    @pytest.mark.parametrize("query", ["", "?for=", "?for=teleport", "?other=rent"])
    def test_without_a_valid_for_nothing_is_counted_and_the_redirect_is_the_same(
        self, api_client, query
    ):
        response = api_client.get(f"/request-access/{query}")

        assert response.status_code == 302
        assert response["Location"] == REQUEST_ACCESS["es"]
        assert AccessInterest.objects.count() == 0

    def test_the_slashless_address_counts_too(self, api_client):
        api_client.get("/request-access?for=shed")

        assert count("shed", "ASKED") == 1

    def test_the_form_is_still_the_one_of_the_browsers_language(self, api_client):
        response = api_client.get("/request-access/?for=rent", HTTP_ACCEPT_LANGUAGE="en")

        assert response["Location"] == REQUEST_ACCESS["en"]

    def test_a_failed_write_still_redirects(self, api_client):
        with patch(
            "hosted.models.AccessInterest.objects.get_or_create", side_effect=Exception("db down")
        ):
            response = api_client.get("/request-access/?for=rent")

        assert response.status_code == 302
        assert response["Location"] == REQUEST_ACCESS["es"]


@pytest.mark.django_db
class TestNobodyIsInTheCount:
    def test_a_row_has_no_column_that_could_hold_a_person_an_address_or_a_browser(self):
        names = {field.name for field in AccessInterest._meta.get_fields()}
        assert names == {"code", "date", "need", "metric", "count"}

    def test_what_the_reader_sends_never_reaches_a_row(self, api_client):
        user = User.objects.create(code="SEEN01", email="seen-reader@your-domain.test")
        api_client.force_authenticate(user)
        seen(
            api_client,
            "rent",
            HTTP_USER_AGENT="Mozilla/5.0 (iPhone) SecretAgent",
            REMOTE_ADDR="203.0.113.7",
        )
        api_client.get("/request-access/?for=rent", HTTP_USER_AGENT="SecretAgent")

        for row in AccessInterest.objects.all():
            held = " ".join(str(getattr(row, f.name)) for f in row._meta.get_fields())
            for secret in (user.code, user.email, "SecretAgent", "203.0.113.7"):
                assert secret not in held.replace(row.code, "")


@pytest.mark.django_db
class TestTheTable:
    def test_one_row_per_day_need_and_metric(self):
        AccessInterest.objects.create(date=date(2026, 10, 21), need="rent", metric="SEEN")
        with pytest.raises(IntegrityError), transaction.atomic():
            AccessInterest.objects.create(date=date(2026, 10, 21), need="rent", metric="SEEN")

    def test_the_admin_only_looks(self):
        model_admin = AccessInterestAdmin(AccessInterest, admin.site)
        request = RequestFactory().get("/")
        request.user = User.objects.create(
            code="SUPER2", email="super2@your-domain.test", is_staff=True, is_superuser=True
        )
        row = AccessInterest.objects.create(date=date(2026, 10, 21), need="rent", metric="SEEN")

        assert model_admin.has_view_permission(request) is True
        assert model_admin.has_add_permission(request) is False
        assert model_admin.has_change_permission(request, row) is False
        assert model_admin.has_delete_permission(request, row) is False

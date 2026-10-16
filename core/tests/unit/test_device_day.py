"""DeviceDay — a daily count per kind of device, holding nobody."""

from datetime import date

import pytest
from django.contrib import admin
from django.db import IntegrityError, transaction
from django.test import RequestFactory

from core.admin import DeviceDayAdmin
from core.models import DeviceDay, User


@pytest.mark.django_db
class TestDeviceDayModel:
    def test_one_row_per_day_device_and_metric(self):
        DeviceDay.objects.create(date=date(2026, 10, 19), device="MOBILE", metric="PEOPLE")
        with pytest.raises(IntegrityError), transaction.atomic():
            DeviceDay.objects.create(date=date(2026, 10, 19), device="MOBILE", metric="PEOPLE")

    def test_same_day_may_hold_other_devices_and_metrics(self):
        day = date(2026, 10, 19)
        DeviceDay.objects.create(date=day, device="MOBILE", metric="PEOPLE")
        DeviceDay.objects.create(date=day, device="OTHER", metric="PEOPLE")
        DeviceDay.objects.create(date=day, device="MOBILE", metric="FORM_SAVES")
        assert DeviceDay.objects.count() == 3

    def test_a_new_row_starts_at_zero_with_a_six_character_code(self):
        row = DeviceDay.objects.create(date=date(2026, 10, 19), device="OTHER", metric="PEOPLE")
        assert row.count == 0
        assert len(row.code) == 6

    def test_the_table_has_no_column_that_could_name_a_person_or_a_browser(self):
        names = {field.name for field in DeviceDay._meta.get_fields()}
        assert names == {"code", "date", "device", "metric", "count"}


@pytest.mark.django_db
class TestDeviceDayAdmin:
    def _request(self):
        request = RequestFactory().get("/")
        request.user = User.objects.create(
            code="SUPER1", email="super@x.test", is_staff=True, is_superuser=True
        )
        return request

    def test_admin_cannot_add_change_or_delete(self):
        model_admin = DeviceDayAdmin(DeviceDay, admin.site)
        request = self._request()
        row = DeviceDay.objects.create(date=date(2026, 10, 19), device="OTHER", metric="PEOPLE")
        assert model_admin.has_add_permission(request) is False
        assert model_admin.has_change_permission(request, row) is False
        assert model_admin.has_delete_permission(request, row) is False

    def test_admin_still_lets_a_superuser_look(self):
        model_admin = DeviceDayAdmin(DeviceDay, admin.site)
        assert model_admin.has_view_permission(self._request()) is True

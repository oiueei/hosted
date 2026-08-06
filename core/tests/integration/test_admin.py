"""Django admin: the two places its default form gets a field wrong.

`User.about` renders as a Textarea rather than a single-line input (S8), and
`Collection.share_token` is not editable at all — see each class below. Both go
through the ModelAdmin/form layer directly: the full HTTP change-form view sits
behind django-otp 2FA (config/urls.py's OTPAdminSite), so fighting that gate
would buy no extra coverage of the thing being tested.

---

User.about renders as a Textarea, not a single-line input (S8).

A CharField renders in the admin as <input type="text"> by default. Pasting a
multi-line Markdown bio into that widget silently strips every newline in the
browser before the value is even submitted — a server-side round-trip test
can't reproduce the browser's paste-time collapsing (Django never sees the
pre-paste text), so what's verifiable here is (a) the admin's generated form
uses a real Textarea for this field, and (b) once Django *does* receive a
multi-line value, saving it through that form preserves the newlines
end-to-end. (The full HTTP change-form view sits behind django-otp 2FA —
config/urls.py's OTPAdminSite — so these go through the ModelAdmin/form layer
directly rather than fighting that gate for marginal extra coverage.)
"""

import json

import pytest
from django import forms
from django.contrib import admin
from django.db import models
from django.forms.models import model_to_dict

from core.admin import CollectionAdmin, UserAdmin
from core.models import Collection, User


@pytest.mark.django_db
class TestUserAdminAboutField:
    def _superuser(self):
        return User.objects.create(
            code="ADMIN1", email="admin@test.com", name="Admin", is_staff=True, is_superuser=True
        )

    def _form_class(self, obj=None):
        request = type("FakeRequest", (), {"user": self._superuser()})()
        return UserAdmin(User, admin.site).get_form(request, obj=obj)

    def test_get_form_uses_a_textarea_widget_for_about(self):
        assert isinstance(self._form_class().base_fields["about"].widget, forms.Textarea)

    def test_a_multiline_bio_round_trips_through_the_admin_form(self):
        target = User.objects.create(code="BIOUSR", email="bio@test.com")
        multiline = "# Comuna Llum\n\nUna colla de coses per compartir.\n\nGràcies!"
        # password has no admin-facing validation here (plain CharField, not
        # the special ReadOnlyPasswordHashField) — model_to_dict returns '' for
        # this passwordless-auth model's unset field, which a required
        # CharField rejects, so give it a placeholder like the admin form would.
        data = {**model_to_dict(target), "about": multiline, "password": "unused-hash"}

        form = self._form_class(obj=target)(data=data, instance=target)
        assert form.is_valid(), form.errors
        form.save()

        target.refresh_from_db()
        assert target.about == multiline


@pytest.mark.django_db
class TestCollectionAdminShareToken:
    """The share token is a bearer credential the admin form must not let anyone type.

    `generate_share_token()` is 22 URL-safe characters from `secrets`; the admin's
    default ModelForm made the column writable, so a superuser could replace that
    with "test" — a link anyone could guess into the collection — with no
    validation between them and the save. Rotating and revoking belong to the
    owner, through CollectionShareLinkView, which always mints a real one.
    """

    def _form_class(self, obj=None):
        superuser = User.objects.create(
            code="ADMIN2", email="admin2@test.com", is_staff=True, is_superuser=True
        )
        request = type("FakeRequest", (), {"user": superuser})()
        return CollectionAdmin(Collection, admin.site).get_form(request, obj=obj)

    def _collection(self):
        owner = User.objects.create(code="OWNR01", email="owner@test.com", name="Owner")
        return Collection.objects.create(
            code="COLL01", owner=owner, headline="Les coses", share_token="a" * 22
        )

    def _post_data(self, collection, **overrides):
        """`model_to_dict`, adapted to what the admin's widgets actually read.

        Two mismatches, neither about the field under test — left unhandled they
        fail the form on `created` and then write NULL into a JSON column:

        - A DateTimeField renders as `AdminSplitDateTime`, which reads
          `created_0` (date) and `created_1` (time). A plain `created` key is
          never looked at, so the field arrives empty and reads as required.
        - A JSONField's widget expects serialised JSON. `model_to_dict` hands
          back a live Python list, which cleans to None and trips the column's
          NOT NULL. Done by field type rather than by name so a new JSONField on
          Collection doesn't quietly reintroduce it.
        """
        data = {**model_to_dict(collection), **overrides}
        created = data.pop("created")
        data["created_0"] = created.date().isoformat()
        data["created_1"] = created.time().isoformat()
        for field in Collection._meta.get_fields():
            if isinstance(field, models.JSONField) and field.name in data:
                data[field.name] = json.dumps(data[field.name])
        return data

    def test_a_hand_typed_share_token_never_reaches_the_row(self):
        collection = self._collection()

        form = self._form_class(obj=collection)(
            data=self._post_data(collection, share_token="guessme"),
            instance=collection,
        )
        assert form.is_valid(), form.errors
        form.save()

        collection.refresh_from_db()
        assert collection.share_token == "a" * 22

    def test_the_rest_of_the_change_form_still_saves(self):
        """The field is read-only, not the form — the unblock still has to work.

        `capacity_unblocked` is the one thing a superuser opens this form to
        change, so a guard that froze the whole row would break the documented
        override.
        """
        collection = self._collection()

        form = self._form_class(obj=collection)(
            data=self._post_data(collection, capacity_unblocked=True),
            instance=collection,
        )
        assert form.is_valid(), form.errors
        form.save()

        collection.refresh_from_db()
        assert collection.capacity_unblocked is True

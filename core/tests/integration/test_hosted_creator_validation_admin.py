"""The operator opens a row for somebody who asked on Tally, and answers it.

**Tests code that is not in the standalone** (see `test_hosted_popin.py` for why the
file sits here).

A request is written in a Tally form now (`hosted/tally.py`), so it reaches the operator
there and not as a row in this table. What the operator needs from the admin is to **make
the row** — find the account by its email, give it a status — and to have the answer go
out as it always did. Pinned here, through the ModelAdmin/form layer (the full HTTP
change-form view sits behind django-otp 2FA, `config/urls.py`'s `OTPAdminSite`; the way
`test_admin.py` does):

- the account is **found by its email**, by autocomplete, and that setup passes Django's
  own admin checks (it needs the related admin to search the field);
- a **new** row asks for the person, the two answers copied from Tally, the status and a
  note; what is typed is kept as typed and what is left empty records that the request was
  sent through Tally; an account cannot have two rows;
- the **answers can be corrected afterwards, and doing so mails nobody**; the account and
  the two moments cannot be edited;
- **a decision made on the form is a decision**: it stamps when, the person is told, and
  the permission follows — for a new row made already approved, and for an edit that turns
  a refusal into a yes; a note on its own, or a status left as it was, tells nobody;
- creating a row and then approving it with the action the operator already used gives the
  permission and the email, as before.
"""

import pytest
from django.contrib import admin as django_admin
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core import mail
from django.test import RequestFactory
from rest_framework import status

from core.admin import UserAdmin
from core.models import User
from hosted.admin import SENT_THROUGH_TALLY, CreatorValidationAdmin
from hosted.models import CreatorValidation
from hosted.tally import REQUEST_ACCESS

STATUS = CreatorValidation.Status


@pytest.fixture(autouse=True)
def hosted_policy(settings):
    settings.CREATOR_POLICY = "hosted.policy.HostedCreatorPolicy"


@pytest.fixture
def operator(db):
    return User.objects.create(
        code="OPER01", email="ops@example.org", is_staff=True, is_superuser=True
    )


@pytest.fixture
def model_admin():
    return CreatorValidationAdmin(CreatorValidation, django_admin.site)


@pytest.fixture
def request_as(operator):
    request = RequestFactory().post("/oiueei-admin/")
    request.user = operator
    request.session = {}
    request._messages = FallbackStorage(request)
    return request


def add(model_admin, request, **data):
    """Submit the add form the way the admin does: validate, build, `save_model`."""
    form = model_admin.get_form(request)(data=data)
    assert form.is_valid(), form.errors
    obj = form.save(commit=False)
    model_admin.save_model(request, obj, form, change=False)
    return obj


def edit(model_admin, request, obj, **data):
    """Submit the change form the way a browser does: pre-filled, so the two answers come
    back as they are unless the test changes them."""
    data = {"who": obj.who, "intent": obj.intent, **data}
    form = model_admin.get_form(request, obj)(data=data, instance=obj)
    assert form.is_valid(), form.errors
    saved = form.save(commit=False)
    model_admin.save_model(request, saved, form, change=True)
    return CreatorValidation.objects.get(pk=saved.pk)


def can_create_a_community(authenticated_client):
    response = authenticated_client.post(
        "/api/v1/collections/", {"headline": "Mercadillo", "mode": "COMMUNITY"}, format="json"
    )
    return response.status_code == status.HTTP_201_CREATED


@pytest.mark.django_db
class TestFindingTheAccountByItsEmail:
    def test_the_user_is_picked_by_autocomplete(self, model_admin):
        assert model_admin.autocomplete_fields == ("user",)

    def test_django_accepts_that_setup(self, model_admin):
        """Autocomplete needs the related admin to be registered and to search: the
        checks say so (admin.E039 / E040) rather than the page failing in front of the
        operator."""
        assert model_admin.check() == []

    def test_the_accounts_admin_finds_an_account_by_its_email(self, user, request_as):
        accounts = django_admin.site._registry[User]
        assert isinstance(accounts, UserAdmin)

        found, _ = accounts.get_search_results(request_as, User.objects.all(), user.email)

        assert list(found) == [user]

    def test_a_part_of_the_address_is_enough(self, user, request_as):
        accounts = django_admin.site._registry[User]

        found, _ = accounts.get_search_results(request_as, User.objects.all(), "test@exam")

        assert user in found


@pytest.mark.django_db
class TestTheFormForANewRow:
    def test_it_asks_for_the_person_the_two_answers_the_status_and_a_note_and_nothing_else(
        self, model_admin, request_as
    ):
        expected = ("user", "who", "intent", "status", "note")

        assert tuple(model_admin.get_form(request_as).base_fields) == expected
        assert model_admin.get_fields(request_as) == expected

    def test_nothing_is_read_only_while_the_row_does_not_exist(self, model_admin, request_as):
        assert model_admin.get_readonly_fields(request_as) == ()
        assert model_admin.get_readonly_fields(request_as, None) == ()

    def test_afterwards_only_the_person_and_the_two_moments_are_read_only(
        self, model_admin, request_as, user
    ):
        row = CreatorValidation.objects.create(user=user, who="x" * 25, intent="y" * 25)

        readonly = model_admin.get_readonly_fields(request_as, row)

        assert set(readonly) == {"user", "created", "resolved"}
        assert model_admin.get_fields(request_as, row) == (
            "user",
            "who",
            "intent",
            "status",
            "note",
            "created",
            "resolved",
        )

    def test_the_answers_typed_are_kept_exactly_as_typed(self, model_admin, request_as, user):
        row = add(
            model_admin,
            request_as,
            user=user.pk,
            who="Runs the Sants repair café",
            intent="A lending shelf for tools",
            status=STATUS.PENDING,
            note="",
        )

        row = CreatorValidation.objects.get(pk=row.pk)
        assert row.who == "Runs the Sants repair café"
        assert row.intent == "A lending shelf for tools"

    @pytest.mark.parametrize(
        ("who", "intent", "expected"),
        [
            ("A neighbour", "", ("A neighbour", SENT_THROUGH_TALLY)),
            ("", "Tools to lend", (SENT_THROUGH_TALLY, "Tools to lend")),
            ("   ", "   ", (SENT_THROUGH_TALLY, SENT_THROUGH_TALLY)),
        ],
    )
    def test_an_answer_left_empty_is_marked_and_the_other_is_kept(
        self, model_admin, request_as, user, who, intent, expected
    ):
        row = add(
            model_admin,
            request_as,
            user=user.pk,
            who=who,
            intent=intent,
            status=STATUS.PENDING,
            note="",
        )

        row = CreatorValidation.objects.get(pk=row.pk)
        assert (row.who, row.intent) == expected

    def test_the_two_answers_are_optional_on_a_new_row(self, model_admin, request_as):
        fields = model_admin.get_form(request_as).base_fields

        assert fields["who"].required is False
        assert fields["intent"].required is False

    @pytest.mark.parametrize(("field", "limit"), [("who", "512"), ("intent", "1024")])
    def test_each_answer_is_a_textarea_with_the_limit_of_its_column(
        self, model_admin, request_as, user, field, limit
    ):
        """A paragraph copied from Tally does not fit in a one-line input, and the browser
        should stop at what the column takes rather than the database refusing it."""
        row = CreatorValidation.objects.create(user=user, who="x" * 25, intent="y" * 25)

        for obj in (None, row):
            html = str(model_admin.get_form(request_as, obj)()[field])

            assert "<textarea" in html
            assert f'maxlength="{limit}"' in html

    def test_a_new_row_with_no_answers_typed_is_marked_as_sent_through_tally(
        self, model_admin, request_as, user
    ):
        row = add(model_admin, request_as, user=user.pk, status=STATUS.PENDING, note="")

        row = CreatorValidation.objects.get(pk=row.pk)
        assert row.who == SENT_THROUGH_TALLY
        assert row.intent == SENT_THROUGH_TALLY
        assert row.status == STATUS.PENDING
        assert row.resolved is None
        assert row.user == user

    def test_a_pending_row_tells_nobody(self, model_admin, request_as, user):
        add(model_admin, request_as, user=user.pk, status=STATUS.PENDING, note="")

        assert mail.outbox == []

    def test_the_note_the_operator_typed_is_kept(self, model_admin, request_as, user):
        row = add(
            model_admin, request_as, user=user.pk, status=STATUS.PENDING, note="Café de Sants"
        )

        assert CreatorValidation.objects.get(pk=row.pk).note == "Café de Sants"

    def test_an_account_cannot_have_two_rows(self, model_admin, request_as, user):
        CreatorValidation.objects.create(user=user, who="x" * 25, intent="y" * 25)

        form = model_admin.get_form(request_as)(data={"user": user.pk, "status": "PENDING"})

        assert not form.is_valid()
        assert "user" in form.errors

    def test_the_status_offers_the_three_answers(self, model_admin, request_as):
        field = model_admin.get_form(request_as).base_fields["status"]

        assert {value for value, _label in field.choices} >= {"PENDING", "APPROVED", "REJECTED"}


@pytest.mark.django_db
class TestCreatingARowAndAnsweringIt:
    def test_create_then_approve_with_the_action_gives_the_permission_and_the_email(
        self, model_admin, request_as, user, authenticated_client
    ):
        add(model_admin, request_as, user=user.pk, status=STATUS.PENDING, note="")
        assert not can_create_a_community(authenticated_client)
        assert mail.outbox == []

        model_admin.approve(request_as, CreatorValidation.objects.filter(user=user))

        row = CreatorValidation.objects.get(user=user)
        assert row.status == STATUS.APPROVED
        assert row.resolved is not None
        assert can_create_a_community(authenticated_client)
        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == [user.email]
        assert "/collections/new" in mail.outbox[0].body

    def test_create_then_reject_with_the_action_tells_them_where_to_ask_again(
        self, model_admin, request_as, user
    ):
        user.language = "ca"
        user.save(update_fields=["language"])
        add(model_admin, request_as, user=user.pk, status=STATUS.PENDING, note="")

        model_admin.reject(request_as, CreatorValidation.objects.filter(user=user))

        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == [user.email]
        assert REQUEST_ACCESS["ca"] in mail.outbox[0].body


@pytest.mark.django_db
class TestCorrectingTheAnswersAfterwards:
    """The two answers are the operator's copy of what was written in Tally: a copy can
    have a typo. Correcting it is not an answer to the person."""

    @pytest.fixture
    def row(self, user):
        return CreatorValidation.objects.create(
            user=user, who="Runs a repair cafe", intent="Tools to lend", status=STATUS.APPROVED
        )

    @pytest.mark.parametrize("field", ["who", "intent"])
    def test_an_answer_can_be_changed_on_an_existing_row(self, model_admin, request_as, row, field):
        saved = edit(
            model_admin,
            request_as,
            row,
            status="APPROVED",
            note="",
            **{field: "Corrected in the admin"},
        )

        assert getattr(saved, field) == "Corrected in the admin"

    @pytest.mark.parametrize("field", ["who", "intent"])
    def test_changing_an_answer_mails_nobody_and_stamps_nothing(
        self, model_admin, request_as, row, field
    ):
        stamp = row.resolved

        saved = edit(
            model_admin,
            request_as,
            row,
            status="APPROVED",
            note="",
            **{field: "Corrected in the admin"},
        )

        assert mail.outbox == []
        assert saved.status == STATUS.APPROVED
        assert saved.resolved == stamp

    def test_the_other_answer_is_left_as_it_was(self, model_admin, request_as, row):
        saved = edit(model_admin, request_as, row, status="APPROVED", note="", who="Corrected")

        assert saved.who == "Corrected"
        assert saved.intent == "Tools to lend"

    @pytest.mark.parametrize("field", ["who", "intent"])
    def test_an_answer_cannot_be_blanked_by_accident(self, model_admin, request_as, row, field):
        """Optional on a new row, required once it exists: a correction that empties the
        field is a slip, and the marker is only for a row opened with nothing to copy."""
        data = {"who": row.who, "intent": row.intent, "status": "APPROVED", "note": "", field: ""}

        form = model_admin.get_form(request_as, row)(data=data, instance=row)

        assert not form.is_valid()
        assert field in form.errors

    def test_the_account_and_the_moments_are_not_in_the_change_form(
        self, model_admin, request_as, row
    ):
        fields = model_admin.get_form(request_as, row).base_fields

        assert set(fields) == {"who", "intent", "status", "note"}


@pytest.mark.django_db
class TestADecisionMadeOnTheForm:
    def test_a_new_row_made_approved_stamps_when_tells_them_and_grants(
        self, model_admin, request_as, user, authenticated_client
    ):
        row = add(model_admin, request_as, user=user.pk, status=STATUS.APPROVED, note="Known")

        row = CreatorValidation.objects.get(pk=row.pk)
        assert row.status == STATUS.APPROVED
        assert row.resolved is not None
        assert row.note == "Known"
        assert [message.to for message in mail.outbox] == [[user.email]]
        assert can_create_a_community(authenticated_client)

    def test_a_new_row_made_approved_with_the_answers_typed_mails_once_and_keeps_them(
        self, model_admin, request_as, user
    ):
        row = add(
            model_admin,
            request_as,
            user=user.pk,
            who="Runs the Sants repair café",
            intent="A lending shelf for tools",
            status=STATUS.APPROVED,
            note="",
        )

        row = CreatorValidation.objects.get(pk=row.pk)
        assert [message.to for message in mail.outbox] == [[user.email]]
        assert (row.who, row.intent) == ("Runs the Sants repair café", "A lending shelf for tools")
        # The answers are the operator's, and they are not what the person is sent.
        message = mail.outbox[0]
        bodies = [message.body, *(content for content, _mime in message.alternatives)]
        assert not any("repair café" in body or "lending shelf" in body for body in bodies)

    def test_a_new_row_made_rejected_tells_them_and_grants_nothing(
        self, model_admin, request_as, user, authenticated_client
    ):
        row = add(model_admin, request_as, user=user.pk, status=STATUS.REJECTED, note="")

        assert CreatorValidation.objects.get(pk=row.pk).resolved is not None
        assert [message.to for message in mail.outbox] == [[user.email]]
        assert not can_create_a_community(authenticated_client)

    def test_turning_a_refusal_into_a_yes_on_the_form_tells_them_again(
        self, model_admin, request_as, user
    ):
        row = CreatorValidation.objects.create(
            user=user, who="x" * 25, intent="y" * 25, status=STATUS.REJECTED
        )

        row = edit(model_admin, request_as, row, status="APPROVED", note="Second thoughts")

        assert row.status == STATUS.APPROVED
        assert row.resolved is not None
        assert len(mail.outbox) == 1
        assert "/collections/new" in mail.outbox[0].body

    def test_the_note_typed_with_the_decision_is_not_wiped(self, model_admin, request_as, user):
        """`resolve()` blanks the note; the form's decision must not."""
        row = CreatorValidation.objects.create(user=user, who="x" * 25, intent="y" * 25)

        row = edit(model_admin, request_as, row, status="REJECTED", note="Reseller, third time")

        assert row.note == "Reseller, third time"

    def test_the_operators_note_never_travels_in_that_email_either(
        self, model_admin, request_as, user
    ):
        row = CreatorValidation.objects.create(user=user, who="x" * 25, intent="y" * 25)

        edit(model_admin, request_as, row, status="REJECTED", note="Too close to a competitor")

        message = mail.outbox[0]
        bodies = [message.body, *(content for content, _mime in message.alternatives)]
        assert not any("competitor" in body for body in bodies)

    def test_a_note_on_its_own_tells_nobody_and_stamps_nothing(self, model_admin, request_as, user):
        row = CreatorValidation.objects.create(
            user=user, who="x" * 25, intent="y" * 25, status=STATUS.APPROVED
        )
        stamp = row.resolved

        row = edit(model_admin, request_as, row, status="APPROVED", note="Remember: invoice sent")

        assert mail.outbox == []
        assert row.note == "Remember: invoice sent"
        assert row.resolved == stamp

    def test_posting_the_same_status_again_tells_nobody(self, model_admin, request_as, user):
        row = CreatorValidation.objects.create(
            user=user, who="x" * 25, intent="y" * 25, status=STATUS.REJECTED
        )

        edit(model_admin, request_as, row, status="REJECTED", note="")

        assert mail.outbox == []

    def test_back_to_pending_clears_the_stamp_and_tells_nobody(self, model_admin, request_as, user):
        row = CreatorValidation.objects.create(user=user, who="x" * 25, intent="y" * 25)
        row.resolve(STATUS.APPROVED)

        row = edit(model_admin, request_as, row, status="PENDING", note="")

        assert row.status == STATUS.PENDING
        assert row.resolved is None
        assert mail.outbox == []

    def test_it_speaks_the_language_of_the_person(self, model_admin, request_as, user):
        user.language = "es"
        user.save(update_fields=["language"])
        add(model_admin, request_as, user=user.pk, status=STATUS.REJECTED, note="")

        assert REQUEST_ACCESS["es"] in mail.outbox[0].body
        assert REQUEST_ACCESS["en"] not in mail.outbox[0].body

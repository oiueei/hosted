"""The answer to a request to run a group here: the model, the admin, the email.

**Tests code that is not in the standalone** (see `test_hosted_popin.py` for why
the file sits here).

A request is made on Tally now (`hosted/tally.py`; it used to be a Django page of our
own at `/request-access/`, with its form, its view and an email to the operator, all
gone). What stays here is what happens when the operator answers it, and what that
answer is made of:

- Approval must be **read**, never written from anywhere but the admin, and **each row
  is resolved in its own right** — one bulk UPDATE would let fifty requests through
  without reading one.
- The person who asked must be **told**, the "no" included: the half that is easy to
  leave out. That is pinned through the admin action the operator actually clicks, not
  through the `resolve()` beneath it.
- A refusal says **where to ask again**: the Tally form (`test_hosted_tally.py` pins which
  one, in each language).
"""

import pytest
from django.contrib import admin as django_admin
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core import mail
from django.test import RequestFactory
from rest_framework import status

from hosted.admin import CreatorValidationAdmin
from hosted.emails import send_creator_validation_decision_email
from hosted.models import CreatorValidation


@pytest.fixture(autouse=True)
def hosted_policy(settings):
    settings.CREATOR_POLICY = "hosted.policy.HostedCreatorPolicy"


@pytest.mark.django_db
class TestTheOperatorsAnswer:
    def test_approving_grants_the_wider_product_and_stamps_when(self, authenticated_client, user):
        validation = CreatorValidation.objects.create(user=user, who="x" * 25, intent="y" * 25)

        validation.resolve(CreatorValidation.Status.APPROVED)

        assert validation.resolved is not None
        response = authenticated_client.post(
            "/api/v1/collections/", {"headline": "Mercadillo", "mode": "COMMUNITY"}, format="json"
        )
        assert response.status_code == status.HTTP_201_CREATED

    def test_a_rejection_leaves_the_open_half_alone(self, authenticated_client, user):
        """A "no" narrows nothing further: they keep the account they had."""
        validation = CreatorValidation.objects.create(user=user, who="x" * 25, intent="y" * 25)

        validation.resolve(CreatorValidation.Status.REJECTED, note="Not this time")

        response = authenticated_client.post(
            "/api/v1/collections/", {"headline": "My shelf"}, format="json"
        )
        assert response.status_code == status.HTTP_201_CREATED

    def test_the_note_is_the_operators_own_memory(self, user):
        """It is recorded, and it is not part of any answer the person receives.

        Pinned because the obvious next feature — "tell them why" — is a
        decision (fase 4), not an oversight, and it must not arrive by accident.
        """
        validation = CreatorValidation.objects.create(user=user, who="x" * 25, intent="y" * 25)

        validation.resolve(CreatorValidation.Status.REJECTED, note="Reseller, third time")

        assert validation.note == "Reseller, third time"


@pytest.mark.django_db
class TestTheAdminActions:
    """The buttons the operator actually presses, in the admin.

    They are the only way an approval happens, so "it works from the shell" is
    not enough — a bulk action that silently touched nothing would look exactly
    like one that worked.
    """

    def _admin_action(self, name, queryset):
        from django.contrib import admin as django_admin

        from hosted.admin import CreatorValidationAdmin

        model_admin = CreatorValidationAdmin(CreatorValidation, django_admin.site)
        request = type("R", (), {"_messages": None})()
        # message_user needs a messages backend; the action's own work is what
        # is under test, so it is stubbed rather than wired to a real request.
        model_admin.message_user = lambda *args, **kwargs: None
        getattr(model_admin, name)(request, queryset)

    def test_approving_from_the_admin_grants_access(self, authenticated_client, user):
        CreatorValidation.objects.create(user=user, who="x" * 25, intent="y" * 25)

        self._admin_action("approve", CreatorValidation.objects.all())

        validation = CreatorValidation.objects.get(user=user)
        assert validation.status == CreatorValidation.Status.APPROVED
        assert validation.resolved is not None
        response = authenticated_client.post(
            "/api/v1/collections/", {"headline": "Mercadillo", "mode": "COMMUNITY"}, format="json"
        )
        assert response.status_code == status.HTTP_201_CREATED

    def test_rejecting_from_the_admin_stamps_the_decision(self, user):
        CreatorValidation.objects.create(user=user, who="x" * 25, intent="y" * 25)

        self._admin_action("reject", CreatorValidation.objects.all())

        validation = CreatorValidation.objects.get(user=user)
        assert validation.status == CreatorValidation.Status.REJECTED
        assert validation.resolved is not None

    def test_each_row_is_resolved_in_its_own_right(self, user, user2):
        """Deliberately not one bulk UPDATE.

        A queryset.update() would be a single query and would skip the
        timestamp entirely — and let somebody wave fifty requests through
        without reading one, which is the opposite of what this table is for.
        """
        for account in (user, user2):
            CreatorValidation.objects.create(user=account, who="x" * 25, intent="y" * 25)

        self._admin_action("approve", CreatorValidation.objects.all())

        stamped = CreatorValidation.objects.exclude(resolved=None)
        assert stamped.count() == 2

    def test_the_account_and_the_moments_of_a_row_cannot_be_edited_here(self):
        """Who it is about and when it was made and answered are the row's own; the two
        answers are the operator's copy from Tally and can be corrected."""
        from django.contrib import admin as django_admin

        from hosted.admin import CreatorValidationAdmin

        model_admin = CreatorValidationAdmin(CreatorValidation, django_admin.site)

        assert set(model_admin.readonly_fields) == {"user", "created", "resolved"}


def _resolve_through_the_admin(validation, action):
    """Run the admin action the operator actually clicks, not `resolve()` beneath it.

    Going through the ModelAdmin is the point: the email is wired to the action,
    and a test that called `resolve()` directly would pass with that wiring
    deleted. `message_user` needs the messages framework, hence the storage.
    """
    request = RequestFactory().post("/oiueei-admin/")
    request.user = validation.user
    request.session = {}
    request._messages = FallbackStorage(request)
    model_admin = CreatorValidationAdmin(CreatorValidation, django_admin.site)
    queryset = CreatorValidation.objects.filter(pk=validation.pk)
    getattr(model_admin, action)(request, queryset)
    validation.refresh_from_db()
    return validation


@pytest.mark.django_db
class TestTheAnswerReachesThePerson:
    def _pending(self, user):
        return CreatorValidation.objects.create(user=user, who="Who", intent="Intent")

    def test_approving_says_so(self, user):
        _resolve_through_the_admin(self._pending(user), "approve")

        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == [user.email]
        assert "approved" in mail.outbox[0].subject.lower()

    def test_rejecting_says_so_too(self, user):
        """The half that is easy to leave out, and the reason the promise on the
        page was a lie for everyone who was not approved."""
        _resolve_through_the_admin(self._pending(user), "reject")

        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == [user.email]

    def test_the_refusal_says_where_to_come_back(self, user):
        _resolve_through_the_admin(self._pending(user), "reject")

        body = mail.outbox[0].body
        # A Tally form (which one depends on the language: `test_hosted_tally.py`) and
        # no longer a page of our own.
        assert "https://tally.so/r/" in body
        assert "/request-access/" not in body

    def test_the_operators_note_never_travels(self, user):
        """`note` is their own memory. A written reason invites an argument about
        rules that are not the product's — the answer is the decision.

        Sent through the sender rather than the admin action, and that is not a
        shortcut: `_resolve` calls `resolve(status)` with no note, and
        `CreatorValidation.resolve` defaults it to `""`, so a request answered
        from the changelist has **no note left** by the time the email is
        composed. A test that went through the action would therefore pass
        against a sender that pasted the note into every line — it did, until a
        mutation caught it saying nothing.
        """
        validation = self._pending(user)
        validation.status = CreatorValidation.Status.REJECTED
        validation.note = "Too close to a competitor of ours"
        validation.save(update_fields=["status", "note"])

        send_creator_validation_decision_email(validation)

        message = mail.outbox[0]
        assert message.alternatives, "no HTML half — checking it would be vacuous"
        bodies = [message.body, *(content for content, _mime in message.alternatives)]
        assert not any("competitor" in body for body in bodies)

    def test_answering_the_same_row_twice_does_not_send_twice(self, user):
        """The operator re-runs the action over a batch; the rows that did not
        move have nothing new to announce."""
        validation = self._pending(user)
        _resolve_through_the_admin(validation, "approve")
        mail.outbox.clear()

        _resolve_through_the_admin(validation, "approve")

        assert mail.outbox == []

    def test_changing_the_answer_does_send_again(self, user):
        validation = self._pending(user)
        _resolve_through_the_admin(validation, "reject")
        mail.outbox.clear()

        _resolve_through_the_admin(validation, "approve")

        assert len(mail.outbox) == 1

    def test_it_speaks_the_language_of_whoever_asked(self, user):
        user.language = "ca"
        user.save(update_fields=["language"])

        _resolve_through_the_admin(self._pending(user), "approve")

        assert "sol·licitud" in mail.outbox[0].subject

    def test_somebody_who_muted_activity_email_is_still_answered(self, user):
        """They asked for this by name. A preference set months ago must not
        swallow the reply — which is why it is Cat. 1 and not Cat. 2."""
        user.notify_activity = False
        user.notify_news = False
        user.save(update_fields=["notify_activity", "notify_news"])

        _resolve_through_the_admin(self._pending(user), "approve")

        assert len(mail.outbox) == 1

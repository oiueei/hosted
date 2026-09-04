"""The form somebody fills in to be allowed to run a group here.

**Tests code that is not in the standalone** (see `test_hosted_popin.py` for why
the file sits here).

It is one page, and almost all of its risk is in who can reach it and what
happens to what they wrote:

- It must recognise a **JWT-cookie session**. The rest of the app authenticates
  that way and a plain Django view would see an anonymous stranger, so the one
  page a logged-in person is sent to would tell them to log in.
- A request must **replace** its predecessor rather than pile up, or an operator
  answers the same person twice and the second answer contradicts the first.
- Approval must be **read**, never written from here.
- And somebody has to be **told**: the operator when a request arrives, the
  person who asked when it is answered. Neither happened until 2026-08-30 — the
  request sat in a table nobody opens while the page promised a reply — so both
  are pinned here, including the half that is easy to leave out (the "no").
"""

import pytest
from django.contrib import admin as django_admin
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core import mail
from django.test import RequestFactory
from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from hosted.admin import CreatorValidationAdmin
from hosted.emails import send_creator_validation_decision_email
from hosted.models import CreatorValidation

URL = "/request-access/"
GOOD = {
    "who": "I run a repair café in Sants, two Saturdays a month.",
    "intent": "A tool library the café's regulars can borrow from and add to.",
}


@pytest.fixture(autouse=True)
def hosted_policy(settings):
    settings.CREATOR_POLICY = "hosted.policy.HostedCreatorPolicy"


@pytest.mark.django_db
class TestReachingThePage:
    def test_a_stranger_is_told_to_sign_in_rather_than_refused(self, api_client):
        """A 403 would be correct and useless: they cannot act on it.

        The page is linked from a notice that says "request access", so whoever
        follows it has already decided to ask. Sending them to /login is the
        answer; a bare Forbidden is a dead end.
        """
        response = api_client.get(URL)

        assert response.status_code == status.HTTP_200_OK
        assert "/login" in response.content.decode()

    def test_a_cookie_session_is_recognised(self, authenticated_client):
        """The whole reason this is a DRF view.

        Auth here is a JWT in a cookie, resolved by CookieJWTAuthentication. A
        `django.views.View` reads `request.user` from the *session*, which this
        app never opens — so the page would show "sign in" to somebody who is
        signed in, on the one page they were sent to.
        """
        response = authenticated_client.get(URL)

        body = response.content.decode()
        assert response.status_code == status.HTTP_200_OK
        assert "Ask to run a group here" in body


@pytest.mark.django_db
class TestTheSlashLessURL:
    """`/request-access`, without the trailing slash — a URL nobody wrote on
    purpose, and the one an address bar or a pasted link produces easily.

    Django's own APPEND_SLASH never rescues it here: that redirect only fires
    when a URL fails to resolve to *anything*, and this one does resolve —
    to the SPA catch-all in `config/urls.py`, which answers every non-static/
    non-api/ non-admin path with `index.html` (200). React Router then took
    over client-side and its `/:userCode` public-profile route, declared ahead
    of this app's own routes, claimed "request-access" as a user code and
    called `GET /api/v1/users/request-access/` — a 404 two layers away from
    the actual mistake, which is what an operator actually saw and reported
    (2026-09). The fix is an explicit redirect in this app's own urlconf,
    mounted ahead of the catch-all for exactly this reason.
    """

    def test_redirects_to_the_slashed_url(self, api_client):
        response = api_client.get("/request-access")

        assert response.status_code == status.HTTP_301_MOVED_PERMANENTLY
        assert response["Location"] == "/request-access/"

    def test_following_it_reaches_the_real_page_not_the_spa(self, api_client):
        response = api_client.get("/request-access", follow=True)

        assert response.status_code == status.HTTP_200_OK
        assert "/login" in response.content.decode()
        # The SPA's index.html never mentions this — proof the redirect landed
        # on the Django page and not on React's catch-all.
        assert '<div id="root">' not in response.content.decode()


@pytest.mark.django_db
class TestSendingARequest:
    def test_it_is_recorded_as_pending_against_that_account(self, authenticated_client, user):
        response = authenticated_client.post(URL, GOOD)

        assert response.status_code == status.HTTP_200_OK
        validation = CreatorValidation.objects.get(user=user)
        assert validation.status == CreatorValidation.Status.PENDING
        assert validation.intent.startswith("A tool library")

    def test_sending_it_grants_nothing_by_itself(self, authenticated_client):
        """The form is not the gate — otherwise anyone types two sentences and
        lets themselves in."""
        authenticated_client.post(URL, GOOD)

        response = authenticated_client.post(
            "/api/v1/collections/", {"headline": "Mercadillo", "mode": "COMMUNITY"}, format="json"
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_an_empty_gesture_is_refused_with_the_form_intact(self, authenticated_client):
        response = authenticated_client.post(URL, {"who": "hi", "intent": "..."})

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert not CreatorValidation.objects.exists()
        # The form comes back rather than a bare error page: they have to be
        # able to fix it without retyping everything.
        assert "Send it" in response.content.decode()

    def test_asking_again_replaces_the_first_request(self, authenticated_client, user):
        """One row per person: the second ask is the same conversation.

        Two rows would mean the operator answers twice, and a rejected request
        sitting beside an approved one makes the policy's own query ambiguous.
        """
        authenticated_client.post(URL, GOOD)
        authenticated_client.post(
            URL, {"who": GOOD["who"], "intent": "Actually a seed library for the allotments."}
        )

        assert CreatorValidation.objects.filter(user=user).count() == 1
        assert CreatorValidation.objects.get(user=user).intent.startswith("Actually a seed")

    def test_asking_again_after_a_no_reopens_it(self, authenticated_client, user):
        CreatorValidation.objects.create(
            user=user,
            who="x" * 25,
            intent="y" * 25,
            status=CreatorValidation.Status.REJECTED,
            resolved=timezone.now(),
        )

        authenticated_client.post(URL, GOOD)

        validation = CreatorValidation.objects.get(user=user)
        assert validation.status == CreatorValidation.Status.PENDING
        # The old decision's timestamp must not linger on a live request.
        assert validation.resolved is None


@pytest.mark.django_db
class TestOnceApproved:
    def test_the_page_stops_asking_and_points_at_the_product(self, authenticated_client, user):
        CreatorValidation.objects.create(
            user=user,
            who="x" * 25,
            intent="y" * 25,
            status=CreatorValidation.Status.APPROVED,
            resolved=timezone.now(),
        )

        body = authenticated_client.get(URL).content.decode()

        assert "You're all set" in body
        assert "Send it" not in body

    def test_a_post_cannot_undo_an_approval(self, authenticated_client, user):
        """Re-submitting must not reset an approved account to PENDING.

        It is the one way this page could take something away from somebody,
        and the most likely route to it is a double-submitted browser tab.
        """
        CreatorValidation.objects.create(
            user=user,
            who="x" * 25,
            intent="y" * 25,
            status=CreatorValidation.Status.APPROVED,
            resolved=timezone.now(),
        )

        authenticated_client.post(URL, GOOD)

        assert CreatorValidation.objects.get(user=user).status == CreatorValidation.Status.APPROVED


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

    def test_the_two_answers_a_person_wrote_cannot_be_edited_here(self):
        """The record is what they sent, not what it was convenient to have sent."""
        from django.contrib import admin as django_admin

        from hosted.admin import CreatorValidationAdmin

        model_admin = CreatorValidationAdmin(CreatorValidation, django_admin.site)

        assert "who" in model_admin.readonly_fields
        assert "intent" in model_admin.readonly_fields


@pytest.fixture
def operator_inbox(monkeypatch):
    """The address this deployment answers on, as a config var (not a setting)."""
    monkeypatch.setenv("CONTACT_EMAIL", "ops@example.org")
    return "ops@example.org"


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
class TestTheOperatorIsTold:
    """A request nobody hears about is a request nobody answers.

    This is what was missing: the row was written, a line went to the security
    log, and that was the whole of it. Requests waited because looking for them
    was something you had to remember to do.
    """

    def test_sending_a_request_mails_the_operator(self, authenticated_client, operator_inbox):
        authenticated_client.post(URL, GOOD)

        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == [operator_inbox]

    def test_it_carries_both_answers_so_the_decision_can_be_made_from_the_email(
        self, authenticated_client, operator_inbox
    ):
        """The two sentences *are* the decision — an alert saying only "someone
        asked" would just be a second thing to go and look up."""
        authenticated_client.post(URL, GOOD)

        body = mail.outbox[0].body
        assert "repair café in Sants" in body
        assert "A tool library" in body

    def test_it_links_the_row_that_answers_it(self, authenticated_client, user, operator_inbox):
        authenticated_client.post(URL, GOOD)

        validation = CreatorValidation.objects.get(user=user)
        path = reverse("admin:hosted_creatorvalidation_change", args=[validation.pk])
        assert path in mail.outbox[0].body

    def test_replying_reaches_the_person_who_asked(
        self, authenticated_client, user, operator_inbox
    ):
        """Half of these need a "tell me more", and that must not require the admin."""
        authenticated_client.post(URL, GOOD)

        assert mail.outbox[0].reply_to == [user.email]

    def test_with_no_contact_address_it_still_goes_somewhere(
        self, authenticated_client, monkeypatch, settings
    ):
        """Unset, the operator mails themselves — the same fallback the contact
        form uses. Silently sending nowhere would restore the original bug."""
        monkeypatch.delenv("CONTACT_EMAIL", raising=False)

        authenticated_client.post(URL, GOOD)

        assert mail.outbox[0].to == [settings.DEFAULT_FROM_EMAIL]

    def test_a_request_that_was_refused_by_the_form_tells_nobody(
        self, authenticated_client, operator_inbox
    ):
        """Nothing was saved, so there is nothing to answer."""
        authenticated_client.post(URL, {"who": "hi", "intent": "..."})

        assert mail.outbox == []


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

        assert URL in mail.outbox[0].body

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

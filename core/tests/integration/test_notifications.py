"""
Integration tests for notification preferences and in-app inbox notifications.

Covers:
- _should_send helper: mandatory always on, activity/news respect user prefs,
  unknown email defaults to send.
- Representative Cat. 2 email (send_booking_decision_email) skips when notify_activity=False.
- Representative Cat. 3 email (send_digest_email) skips when notify_news=False.
- Cat. 1 email (send_magic_link_email) always sent regardless of prefs.
- PATCH /api/v1/users/{code}/ accepts notify_activity / notify_news.
- Token endpoint GET/PATCH round-trip; rejects invalid tokens.
- InAppNotification created for all user-action-triggered events.
"""

from unittest.mock import patch

import pytest
from django.core import mail
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from core.models import FAQ, RSVP, BookingPeriod, Collection, Thing, User
from core.models.notification import InAppNotification
from core.services.email_service import (
    CATEGORY_ACTIVITY,
    CATEGORY_MANDATORY,
    CATEGORY_NEWS,
    _should_send,
    make_digest_mute_token,
    make_notifications_token,
    send_booking_decision_email,
    send_digest_email,
    send_invite_rejected_email,
    send_magic_link_email,
)


@pytest.fixture
def noti_user(db):
    return User.objects.create(
        code="NOTI01", email="noti1@test.com", name="Prefs User", notify_news=True
    )


def test_new_user_starts_subscribed_to_both_categories(db):
    """A new user receives both activity and news without opting in.

    News (Cat. 3 — the digest) defaulted OFF until the 2026-08 design round, and
    the digest consequently reached almost nobody. Turning it on is only
    compatible with DESIGN §6 because of the per-collection mute below: the way
    out of one group's summaries no longer costs you the transactional email you
    need. If that mute is ever removed, this default has to go back to False.
    """
    fresh = User.objects.create(code="NEW01", email="new@test.com", name="Fresh")
    assert fresh.notify_news is True
    assert fresh.notify_activity is True


def test_new_collection_sends_a_weekly_digest_by_default(db):
    """A new collection is born sending a weekly summary.

    The other half of the same 2026-08 change: `notify_news` defaulting on is
    worth nothing while every collection defaults to `NONE`, which is the state
    that made the digest unreachable. Both ends had to move, and the Create form
    has to show the field (it didn't) so an owner isn't mailing their members
    without knowing.
    """
    owner = User.objects.create(code="DGDEF1", email="dgdef@test.com", name="Owner")
    collection = Collection.objects.create(code="DGDEF2", owner=owner, headline="Fresh")
    assert collection.digest_frequency == Collection.DigestFrequency.WEEKLY


def test_muting_one_collection_stops_only_that_digest(db, noti_user):
    """A member who silences a group stops that group's digest and no other.

    This is the guarantee that makes notify_news default True defensible, so it
    is asserted on both sides: the muted collection sends nothing, an unmuted
    one still lands in the same person's inbox.
    """
    owner = User.objects.create(code="DGOWN1", email="dgown@test.com", name="Owner")
    noisy = Collection.objects.create(code="DGNOI1", owner=owner, headline="Noisy")
    quiet = Collection.objects.create(code="DGQUI1", owner=owner, headline="Quiet")
    for col in (noisy, quiet):
        col.invites.add(noti_user)
    noisy.digest_muted.add(noti_user)

    mail.outbox.clear()
    send_digest_email("Noisy", noisy.code, ["A thing"], [noti_user.email], collection=noisy)
    assert mail.outbox == [], "the muted collection must not reach this member"

    send_digest_email("Quiet", quiet.code, ["A thing"], [noti_user.email], collection=quiet)
    assert len(mail.outbox) == 1, "muting one group must not silence the others"


def test_muting_a_collection_leaves_its_activity_email_alone(db, noti_user):
    """The mute is about a group's news, not about the group.

    A member who silences the weekly summary still has to hear that their own
    hold was decided — the whole point of keeping the two categories apart.
    """
    owner = User.objects.create(code="DGOWN2", email="dgown2@test.com", name="Owner")
    collection = Collection.objects.create(code="DGCOL2", owner=owner, headline="Group")
    collection.invites.add(noti_user)
    collection.digest_muted.add(noti_user)

    mail.outbox.clear()
    assert _should_send(noti_user.email, CATEGORY_ACTIVITY, collection=collection) is True
    assert _should_send(noti_user.email, CATEGORY_NEWS, collection=collection) is False


def test_should_send_mandatory_always_true(db, noti_user):
    noti_user.notify_activity = False
    noti_user.notify_news = False
    noti_user.save()
    assert _should_send(noti_user.email, CATEGORY_MANDATORY) is True


def test_should_send_respects_activity_and_news(db, noti_user):
    noti_user.notify_activity = False
    noti_user.notify_news = True
    noti_user.save()
    assert _should_send(noti_user.email, CATEGORY_ACTIVITY) is False
    assert _should_send(noti_user.email, CATEGORY_NEWS) is True


def test_should_send_unknown_email_defaults_to_true(db):
    assert _should_send("stranger@nowhere.test", CATEGORY_ACTIVITY) is True
    assert _should_send("stranger@nowhere.test", CATEGORY_NEWS) is True


def test_magic_link_always_sent_even_when_opted_out(db, noti_user):
    noti_user.notify_activity = False
    noti_user.notify_news = False
    noti_user.save()
    mail.outbox.clear()
    send_magic_link_email(noti_user.email, "http://example.com/magic/ABC123")
    assert len(mail.outbox) == 1


def test_activity_email_skipped_when_opted_out(db, noti_user):
    owner = User.objects.create(code="OWN001", email="owner@test.com", name="Owner")
    collection = Collection.objects.create(code="COL001", owner=owner, headline="Club")
    thing = Thing.objects.create(code="THG001", owner=owner, headline="Item")
    collection.things.add(thing)
    booking = BookingPeriod.objects.create(
        code="BKG001",
        thing_code=thing,
        requester_code=noti_user,
        requester_email=noti_user.email,
        owner_code=owner,
        status="ACCEPTED",
    )

    noti_user.notify_activity = False
    noti_user.save()
    mail.outbox.clear()
    send_booking_decision_email(booking, thing, accepted=True)
    assert len(mail.outbox) == 0

    noti_user.notify_activity = True
    noti_user.save()
    send_booking_decision_email(booking, thing, accepted=True)
    assert len(mail.outbox) == 1


def test_invite_rejected_email_content(db):
    """Previously only asserted through mocks in test_views.py/test_notifications.py
    — never verified a real message reached mail.outbox with the right content."""
    mail.outbox.clear()
    send_invite_rejected_email("Jamie", "Book Club", "owner3@test.com")
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == ["owner3@test.com"]
    assert "Jamie" in mail.outbox[0].body
    assert "Book Club" in mail.outbox[0].body


def test_news_email_skipped_when_opted_out(db, noti_user):
    second = User.objects.create(
        code="NOTI02", email="noti2@test.com", name="Second", notify_news=True
    )
    noti_user.notify_news = False
    noti_user.save()
    mail.outbox.clear()

    send_digest_email("Club", "COLL01", ["Thing A"], [noti_user.email, second.email])
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == [second.email]


def test_member_can_mute_and_unmute_a_collection_digest(db, noti_user):
    """The member-facing switch round-trips, and the serializer reports it back.

    `is_digest_muted` is what renders the toggle in its correct position, so a
    mute the API accepted but the read endpoint denied would leave the member
    clicking a control that springs back on every reload.
    """
    owner = User.objects.create(code="DGOWN3", email="dgown3@test.com", name="Owner")
    collection = Collection.objects.create(
        code="DGCOL3", owner=owner, headline="Group", visibility=Collection.Visibility.PUBLIC
    )
    collection.invites.add(noti_user)
    client = APIClient()
    token = RefreshToken.for_user(noti_user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")

    resp = client.post(
        f"/api/v1/collections/{collection.code}/digest/", {"muted": True}, format="json"
    )
    assert resp.status_code == 200
    assert collection.digest_muted.filter(code=noti_user.code).exists()
    assert client.get(f"/api/v1/collections/{collection.code}/").data["is_digest_muted"] is True

    resp = client.post(
        f"/api/v1/collections/{collection.code}/digest/", {"muted": False}, format="json"
    )
    assert resp.status_code == 200
    assert not collection.digest_muted.filter(code=noti_user.code).exists()
    assert client.get(f"/api/v1/collections/{collection.code}/").data["is_digest_muted"] is False


def test_digest_pref_rejects_a_body_without_a_boolean(db, noti_user):
    """A missing or non-boolean `muted` is a 400, not a silent un-mute.

    The view reads the flag straight from the body, so a typo'd or absent field
    falling through to `else: remove()` would quietly re-subscribe someone who
    asked to be left alone.
    """
    owner = User.objects.create(code="DGOWN6", email="dgown6@test.com", name="Owner")
    collection = Collection.objects.create(code="DGCOL6", owner=owner, headline="Group")
    collection.invites.add(noti_user)
    collection.digest_muted.add(noti_user)
    client = APIClient()
    token = RefreshToken.for_user(noti_user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")

    for body in ({}, {"muted": "false"}, {"muted": None}):
        resp = client.post(f"/api/v1/collections/{collection.code}/digest/", body, format="json")
        assert resp.status_code == 400, f"{body} should not be accepted"
    assert collection.digest_muted.filter(code=noti_user.code).exists(), (
        "a rejected request must leave the existing preference untouched"
    )


def test_non_member_cannot_mute_a_collection_digest(db, noti_user):
    """A stranger's POST must not write a row against someone else's group.

    The endpoint is unguarded by any object permission class, so membership is
    the only thing standing between an arbitrary code and a write.
    """
    owner = User.objects.create(code="DGOWN4", email="dgown4@test.com", name="Owner")
    collection = Collection.objects.create(
        code="DGCOL4", owner=owner, headline="Not yours", visibility=Collection.Visibility.PUBLIC
    )
    client = APIClient()
    token = RefreshToken.for_user(noti_user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")

    resp = client.post(
        f"/api/v1/collections/{collection.code}/digest/", {"muted": True}, format="json"
    )
    assert resp.status_code == 400
    assert collection.digest_muted.count() == 0, "the denied request must not have written"


def test_digest_footer_link_mutes_that_collection_without_a_login(db, noti_user):
    """The unsubscribe in the digest footer works for someone with no session.

    This is the whole justification for notify_news defaulting to True: if the
    one-click exit needed a login it would be harder to leave than to be
    enrolled, which is the DESIGN §6 line.
    """
    owner = User.objects.create(code="DGOWN5", email="dgown5@test.com", name="Owner")
    collection = Collection.objects.create(code="DGCOL5", owner=owner, headline="Group")
    collection.invites.add(noti_user)

    mail.outbox.clear()
    send_digest_email(
        "Group", collection.code, ["A thing"], [noti_user.email], collection=collection
    )
    assert len(mail.outbox) == 1
    token = make_digest_mute_token(noti_user, collection)
    assert f"/digest/mute/{token}" in mail.outbox[0].body, "the footer must carry the link"

    # No credentials — an unauthenticated client, as from a mail app.
    resp = APIClient().post(f"/api/v1/digest/mute/{token}/")
    assert resp.status_code == 200
    assert collection.digest_muted.filter(code=noti_user.code).exists()

    mail.outbox.clear()
    send_digest_email(
        "Group", collection.code, ["A thing"], [noti_user.email], collection=collection
    )
    assert mail.outbox == [], "the next digest must not be sent after unsubscribing"


def test_digest_mute_token_rejects_a_tampered_signature(db):
    """An unsigned or edited token must not write anything.

    The token names both the user and the collection, so a forgeable one would
    let anybody unsubscribe anybody from any group.
    """
    resp = APIClient().post("/api/v1/digest/mute/NOTI01:DGCOL5/")
    assert resp.status_code == 401


def test_patch_me_updates_prefs(db, noti_user):
    client = APIClient()
    token = RefreshToken.for_user(noti_user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")

    resp = client.put(
        f"/api/v1/users/{noti_user.code}/",
        {"notify_activity": False, "notify_news": False},
        format="json",
    )
    assert resp.status_code == 200
    noti_user.refresh_from_db()
    assert noti_user.notify_activity is False
    assert noti_user.notify_news is False


def test_notifications_token_endpoint_round_trip(db, noti_user):
    client = APIClient()
    token = make_notifications_token(noti_user)

    resp = client.get(f"/api/v1/notifications/token/{token}/")
    assert resp.status_code == 200
    assert resp.json() == {"notify_activity": True, "notify_news": True}

    resp = client.patch(
        f"/api/v1/notifications/token/{token}/",
        {"notify_news": False},
        format="json",
    )
    assert resp.status_code == 200
    noti_user.refresh_from_db()
    assert noti_user.notify_news is False
    assert noti_user.notify_activity is True


def test_notifications_token_rejects_invalid(db):
    client = APIClient()
    resp = client.get("/api/v1/notifications/token/not-a-real-token/")
    assert resp.status_code == 401


def test_notifications_token_is_salt_scoped(db, noti_user):
    """L3: the prefs token is a TimestampSigner signature scoped to the
    'notifications-prefs' salt — a valid one resolves to the user, but a
    signature minted with another salt (or garbage) is rejected."""
    from django.core.signing import TimestampSigner

    from core.services.email_service import verify_notifications_token

    assert verify_notifications_token(make_notifications_token(noti_user)) == noti_user.code
    # Same payload, different salt → not a valid prefs token here.
    other = TimestampSigner(salt="something-else").sign(noti_user.code)
    assert verify_notifications_token(other) is None
    assert verify_notifications_token("garbage") is None


# ---------------------------------------------------------------------------
# InAppNotification creation tests
# ---------------------------------------------------------------------------


def _make_client(user):
    client = APIClient()
    token = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")
    return client


def _make_booking(owner, requester, thing, thing_type="GIFT_THING"):
    return BookingPeriod.objects.create(
        thing_code=thing,
        thing_type=thing_type,
        requester_code=requester,
        requester_email=requester.email,
        owner_code=owner,
        status="PENDING",
    )


@pytest.fixture
def two_users(db):
    owner = User.objects.create(code="OWN001", email="owner@test.com", name="Owner")
    requester = User.objects.create(code="REQ001", email="requester@test.com", name="Requester")
    return owner, requester


@pytest.fixture
def thing_with_collection(db, two_users):
    owner, requester = two_users
    thing = Thing.objects.create(code="THG001", owner=owner, headline="My Thing", type="GIFT_THING")
    collection = Collection.objects.create(code="COL001", owner=owner, headline="My Collection")
    collection.things.add(thing)
    collection.invites.add(requester)
    return thing, collection


@pytest.mark.django_db
def test_booking_accept_via_api_creates_in_app_notification(two_users, thing_with_collection):
    owner, requester = two_users
    thing, _ = thing_with_collection
    booking = _make_booking(owner, requester, thing)
    client = _make_client(owner)

    with patch("core.services.email_service.send_booking_decision_email"):
        resp = client.post(f"/api/v1/bookings/{booking.code}/accept/")

    assert resp.status_code == status.HTTP_200_OK
    notif = InAppNotification.objects.get(
        user=requester, type=InAppNotification.Type.BOOKING_ACCEPTED
    )
    assert notif.payload["thing_headline"] == thing.headline
    assert notif.payload["owner_name"] == owner.name


@pytest.mark.django_db
def test_booking_reject_via_api_creates_in_app_notification(two_users, thing_with_collection):
    owner, requester = two_users
    thing, _ = thing_with_collection
    booking = _make_booking(owner, requester, thing)
    client = _make_client(owner)

    with patch("core.services.email_service.send_booking_decision_email"):
        resp = client.post(f"/api/v1/bookings/{booking.code}/reject/")

    assert resp.status_code == status.HTTP_200_OK
    notif = InAppNotification.objects.get(
        user=requester, type=InAppNotification.Type.BOOKING_REJECTED
    )
    assert notif.payload["thing_headline"] == thing.headline


@pytest.mark.django_db
def test_booking_accept_via_rsvp_creates_in_app_notification(two_users, thing_with_collection):
    owner, requester = two_users
    thing, _ = thing_with_collection
    booking = _make_booking(owner, requester, thing)
    rsvp = RSVP.objects.create(
        user_code=owner,
        user_email=owner.email,
        action="BOOKING_ACCEPT",
        target_code=booking.code,
    )
    client = APIClient()

    with patch("core.services.email_service.send_booking_decision_email"):
        resp = client.post(f"/api/v1/auth/verify/{rsvp.token}/")

    assert resp.status_code == status.HTTP_200_OK
    assert InAppNotification.objects.filter(
        user=requester, type=InAppNotification.Type.BOOKING_ACCEPTED
    ).exists()


@pytest.mark.django_db
def test_booking_request_creates_in_app_notification_for_owner(two_users, thing_with_collection):
    owner, requester = two_users
    thing, _ = thing_with_collection
    client = _make_client(requester)

    with (
        patch("core.services.email_service.send_booking_request_email"),
        patch("core.services.email_service.send_booking_confirmation_email"),
    ):
        resp = client.post(f"/api/v1/things/{thing.code}/request/", {}, format="json")

    assert resp.status_code == status.HTTP_201_CREATED
    notif = InAppNotification.objects.get(user=owner, type=InAppNotification.Type.BOOKING_REQUESTED)
    assert notif.payload["thing_headline"] == thing.headline
    assert notif.payload["requester_name"] == requester.name


@pytest.mark.django_db
def test_faq_question_creates_in_app_notification_for_owner(two_users, thing_with_collection):
    owner, requester = two_users
    thing, _ = thing_with_collection
    client = _make_client(requester)

    with patch("core.views.faq.send_faq_question_email"):
        resp = client.post(
            f"/api/v1/things/{thing.code}/faq/", {"question": "Is this available?"}, format="json"
        )

    assert resp.status_code == status.HTTP_201_CREATED
    notif = InAppNotification.objects.get(user=owner, type=InAppNotification.Type.FAQ_QUESTION)
    assert notif.payload["thing_headline"] == thing.headline
    assert notif.payload["questioner_name"] == requester.name


@pytest.mark.django_db
def test_faq_answer_creates_in_app_notification_for_questioner(two_users, thing_with_collection):
    owner, requester = two_users
    thing, _ = thing_with_collection
    faq = FAQ.objects.create(
        code="FAQ001",
        thing=thing,
        questioner=requester,
        question="Is this available?",
    )
    client = _make_client(owner)

    with patch("core.views.faq.send_faq_answer_email"):
        resp = client.post(f"/api/v1/faq/{faq.code}/answer/", {"answer": "Yes!"}, format="json")

    assert resp.status_code == status.HTTP_200_OK
    notif = InAppNotification.objects.get(user=requester, type=InAppNotification.Type.FAQ_ANSWERED)
    assert notif.payload["thing_headline"] == thing.headline


@pytest.mark.django_db
def test_faq_hide_creates_in_app_notification_for_questioner(two_users, thing_with_collection):
    owner, requester = two_users
    thing, _ = thing_with_collection
    faq = FAQ.objects.create(
        code="FAQ002",
        thing=thing,
        questioner=requester,
        question="Is this available?",
    )
    client = _make_client(owner)

    with patch("core.views.faq.send_faq_hide_email"):
        resp = client.post(f"/api/v1/faq/{faq.code}/hide/")

    assert resp.status_code == status.HTTP_200_OK
    notif = InAppNotification.objects.get(user=requester, type=InAppNotification.Type.FAQ_HIDDEN)
    assert notif.payload["thing_headline"] == thing.headline


@pytest.mark.django_db
def test_invite_rejected_creates_in_app_notification_for_owner(two_users):
    owner, invitee = two_users
    collection = Collection.objects.create(code="COL003", owner=owner, headline="My Collection")
    rsvp = RSVP.objects.create(
        user_code=invitee,
        user_email=invitee.email,
        action="COLLECTION_REJECT",
        target_code=collection.code,
    )
    client = APIClient()

    with patch("core.views.auth.send_invite_rejected_email"):
        resp = client.get(f"/api/v1/auth/verify/{rsvp.token}/")

    assert resp.status_code == status.HTTP_200_OK
    notif = InAppNotification.objects.get(user=owner, type=InAppNotification.Type.INVITE_REJECTED)
    assert notif.payload["collection_headline"] == collection.headline
    assert notif.payload["invitee_name"] == invitee.name


@pytest.mark.django_db
def test_collection_revoke_creates_in_app_notification_for_removed_user(two_users):
    owner, invitee = two_users
    collection = Collection.objects.create(code="COL004", owner=owner, headline="My Collection")
    collection.invites.add(invitee)
    client = _make_client(owner)

    with patch("core.views.collections.send_collection_revoke_email"):
        resp = client.delete(
            f"/api/v1/collections/{collection.code}/invite/",
            {"user_code": invitee.code},
            format="json",
        )

    assert resp.status_code == status.HTTP_200_OK
    notif = InAppNotification.objects.get(
        user=invitee, type=InAppNotification.Type.COLLECTION_REVOKED
    )
    assert notif.payload["collection_headline"] == collection.headline


# ---------------------------------------------------------------------------
# Inbox endpoint tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_inbox_get_returns_notifications_for_authenticated_user(two_users):
    owner, requester = two_users
    InAppNotification.objects.create(
        code="NTF001",
        user=owner,
        type=InAppNotification.Type.BOOKING_ACCEPTED,
        payload={"thing_headline": "Widget"},
    )
    InAppNotification.objects.create(
        code="NTF002",
        user=requester,
        type=InAppNotification.Type.BOOKING_REJECTED,
        payload={"thing_headline": "Gadget"},
    )
    client = _make_client(owner)

    resp = client.get("/api/v1/inbox/")

    assert resp.status_code == status.HTTP_200_OK
    assert len(resp.data) == 1
    assert resp.data[0]["code"] == "NTF001"
    assert resp.data[0]["type"] == InAppNotification.Type.BOOKING_ACCEPTED
    assert resp.data[0]["payload"]["thing_headline"] == "Widget"


@pytest.mark.django_db
def test_inbox_get_returns_empty_list_when_no_notifications(two_users):
    owner, _ = two_users
    client = _make_client(owner)

    resp = client.get("/api/v1/inbox/")

    assert resp.status_code == status.HTTP_200_OK
    assert resp.data == []


@pytest.mark.django_db
def test_inbox_get_requires_authentication():
    client = APIClient()
    resp = client.get("/api/v1/inbox/")
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_inbox_delete_removes_notification(two_users):
    owner, _ = two_users
    notif = InAppNotification.objects.create(
        code="NTF003",
        user=owner,
        type=InAppNotification.Type.BOOKING_ACCEPTED,
        payload={},
    )
    client = _make_client(owner)

    resp = client.delete(f"/api/v1/inbox/{notif.code}/")

    assert resp.status_code == 204
    assert not InAppNotification.objects.filter(code="NTF003").exists()


@pytest.mark.django_db
def test_inbox_delete_cannot_remove_other_users_notification(two_users):
    owner, requester = two_users
    notif = InAppNotification.objects.create(
        code="NTF004",
        user=owner,
        type=InAppNotification.Type.BOOKING_ACCEPTED,
        payload={},
    )
    client = _make_client(requester)

    resp = client.delete(f"/api/v1/inbox/{notif.code}/")

    assert resp.status_code == 404
    assert InAppNotification.objects.filter(code="NTF004").exists()


@pytest.mark.django_db
def test_inbox_delete_nonexistent_notification_returns_404(two_users):
    owner, _ = two_users
    client = _make_client(owner)

    resp = client.delete("/api/v1/inbox/ZZZZZZ/")

    assert resp.status_code == 404


@pytest.mark.django_db
def test_inbox_get_on_item_route_returns_405_not_500(two_users):
    # GET /inbox/{code}/ is not a feature (only the collection is listable). The
    # crossed route must return a clean 405, not a TypeError-driven 500.
    owner, _ = two_users
    client = _make_client(owner)

    resp = client.get("/api/v1/inbox/ANYCOD/")

    assert resp.status_code == 405


@pytest.mark.django_db
def test_inbox_delete_on_collection_route_returns_405_not_500(two_users):
    # DELETE /inbox/ has no target notification — a clean 405, not a 500.
    owner, _ = two_users
    client = _make_client(owner)

    resp = client.delete("/api/v1/inbox/")

    assert resp.status_code == 405

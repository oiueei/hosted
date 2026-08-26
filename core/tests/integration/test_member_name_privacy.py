"""L2, the notification half: nobody is identified to a stranger by their address.

`User.display_name` falls back to the email when `name` is empty, and `name` is
empty for **every** account made by `get_or_create(email=email)` — everyone who
arrived by magic link or invitation and never filled in a profile. So the
fallback is the ordinary state of a new member, not an exotic one, and every
notification path that reached for `display_name` was handing that member's
address to whoever it notified.

`TestCoMemberNameLeak` in `unit/test_serializers.py` pins the same rule for the
serializers. This file pins the paths a serializer never sees: the outbound
emails and the in-app notification payloads.

**Each test drives a view**, deliberately. Calling the sender with `""` would
only prove `email_service._member_name` works; it would stay green if a caller
went back to passing `display_name`, which is the mistake that actually
happened. What is under test here is the whole path, caller included.
"""

import pytest
from django.core import mail

from core.models import RSVP, Collection, Thing, User
from core.models.booking import BookingPeriod
from core.models.notification import InAppNotification

NAMELESS = "nameless-owner@example.com"


def _bodies():
    """Every rendered part of every message sent so far, as one string."""
    parts = []
    for message in mail.outbox:
        parts.append(message.subject)
        parts.append(message.body)
        parts.extend(str(alt) for alt, _ in message.alternatives)
    return "\n".join(parts)


@pytest.fixture
def nameless_owner(db):
    """Somebody who signed in once and never filled in their profile."""
    return User.objects.create(code="NONAME", email=NAMELESS, name="")


@pytest.fixture
def nameless_client(api_client, nameless_owner):
    from rest_framework_simplejwt.tokens import RefreshToken

    refresh = RefreshToken.for_user(nameless_owner)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
    return api_client


@pytest.mark.django_db
class TestTheAskerIsNotIdentifiedByTheirAddress:
    def test_a_nameless_asker_is_not_named_by_email_to_the_thing_owner(
        self, api_client, user, collection, thing
    ):
        """In a COMMUNITY group the thing's owner is a co-member, and no FAQ
        field ever serves them the asker's address. The notification must not be
        the one thing that does."""
        from rest_framework_simplejwt.tokens import RefreshToken

        asker = User.objects.create(code="ASKNON", email="asker@example.com", name="")
        collection.invites.add(asker)  # a co-member, which is who asks questions
        refresh = RefreshToken.for_user(asker)
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
        mail.outbox.clear()

        res = api_client.post(
            f"/api/v1/things/{thing.code}/faq/", {"question": "Does it work?"}, format="json"
        )
        assert res.status_code == 201

        assert "asker@example.com" not in _bodies()
        payload = InAppNotification.objects.get(user=user, type="FAQ_QUESTION").payload
        assert payload["questioner_name"] != "asker@example.com"


@pytest.mark.django_db
class TestTheThingOwnerIsNotIdentifiedByTheirAddress:
    def test_a_nameless_owner_answering_does_not_hand_over_their_address(
        self, api_client, nameless_owner, nameless_client, user2
    ):
        """The person who asked gets an answer, not the answerer's mailbox."""
        from core.models import FAQ

        thing = Thing.objects.create(code="FAQTH1", owner=nameless_owner, headline="Drill")
        faq = FAQ.objects.create(code="FAQP01", thing=thing, questioner=user2, question="Works?")
        mail.outbox.clear()

        res = nameless_client.post(
            f"/api/v1/faq/{faq.code}/answer/", {"answer": "Yes"}, format="json"
        )
        assert res.status_code == 200

        assert NAMELESS not in _bodies()
        payload = InAppNotification.objects.get(user=user2, type="FAQ_ANSWERED").payload
        assert payload["owner_name"] != NAMELESS

    def test_a_nameless_owner_hiding_a_question_does_not_hand_over_their_address(
        self, nameless_owner, nameless_client, user2
    ):
        from core.models import FAQ

        thing = Thing.objects.create(code="FAQTH2", owner=nameless_owner, headline="Drill")
        faq = FAQ.objects.create(code="FAQP02", thing=thing, questioner=user2, question="Works?")
        mail.outbox.clear()

        res = nameless_client.post(f"/api/v1/faq/{faq.code}/hide/", {}, format="json")
        assert res.status_code == 200

        assert NAMELESS not in _bodies()
        payload = InAppNotification.objects.get(user=user2, type="FAQ_HIDDEN").payload
        assert payload["owner_name"] != NAMELESS


@pytest.mark.django_db
class TestTheGroupOwnerIsNotIdentifiedByTheirAddress:
    def test_an_invitation_from_a_nameless_owner_does_not_carry_their_address(
        self, nameless_owner, nameless_client
    ):
        """The invitee is a stranger who has agreed to nothing yet — the one
        reader who must never be handed an address by accident."""
        collection = Collection.objects.create(
            code="INVCOL", owner=nameless_owner, headline="Tools"
        )
        mail.outbox.clear()

        res = nameless_client.post(
            f"/api/v1/collections/{collection.code}/invite/",
            {"email": "stranger@example.com"},
            format="json",
        )
        assert res.status_code == 200
        assert mail.outbox, "the invitation should have been sent"
        assert NAMELESS not in _bodies()

    def test_a_bulk_invitation_from_a_nameless_owner_does_not_carry_their_address(
        self, nameless_owner, nameless_client
    ):
        """The bulk endpoint composes its own fan-out rather than going through
        `deliver_invitation`, so it needs its own guard."""
        collection = Collection.objects.create(
            code="BLKCOL", owner=nameless_owner, headline="Tools"
        )
        mail.outbox.clear()

        res = nameless_client.post(
            f"/api/v1/collections/{collection.code}/invite/bulk/",
            {"invites": [{"email": "stranger2@example.com"}]},
            format="json",
        )
        assert res.status_code == 200
        assert mail.outbox, "the bulk invitation should have been sent"
        assert NAMELESS not in _bodies()

    def test_removing_a_member_does_not_hand_them_the_owners_address(
        self, nameless_owner, nameless_client, user2
    ):
        """The person being shown the door is the last reader who should leave
        holding the owner's mailbox."""
        collection = Collection.objects.create(
            code="REVCOL", owner=nameless_owner, headline="Tools"
        )
        collection.invites.add(user2)
        mail.outbox.clear()

        res = nameless_client.delete(
            f"/api/v1/collections/{collection.code}/invite/",
            {"user_code": user2.code},
            format="json",
        )
        assert res.status_code == 200

        assert NAMELESS not in _bodies()
        payload = InAppNotification.objects.get(user=user2, type="COLLECTION_REVOKED").payload
        assert payload["owner_name"] != NAMELESS

    def test_deleting_a_collection_does_not_hand_members_the_owners_address(
        self, nameless_owner, nameless_client, user2
    ):
        collection = Collection.objects.create(
            code="DELCOL", owner=nameless_owner, headline="Tools"
        )
        collection.invites.add(user2)

        res = nameless_client.delete(f"/api/v1/collections/{collection.code}/")
        assert res.status_code == 204

        payload = InAppNotification.objects.get(user=user2, type="COLLECTION_DELETED").payload
        assert payload["owner_name"] != NAMELESS

    def test_a_broadcast_does_not_render_the_owners_address_as_their_name(
        self, nameless_owner, nameless_client, user2
    ):
        """The broadcast carries a Reply-To, so the address is disclosed either
        way and the owner is told so before sending. That is a disclosure they
        make knowingly — printing it as their *name* in the body and in every
        member's inbox is a different thing, and not what it means."""
        collection = Collection.objects.create(
            code="BRDCOL", owner=nameless_owner, headline="Tools"
        )
        collection.invites.add(user2)
        mail.outbox.clear()

        res = nameless_client.post(
            f"/api/v1/collections/{collection.code}/broadcast/",
            {"message": "Meeting on Friday"},
            format="json",
        )
        assert res.status_code == 200

        payload = InAppNotification.objects.get(user=user2, type="BROADCAST").payload
        assert payload["owner_name"] != NAMELESS
        # The Reply-To is the deliberate disclosure and must survive this change.
        assert mail.outbox[0].reply_to == [NAMELESS]

    def test_approving_a_members_suggestion_does_not_carry_the_owners_address(
        self, nameless_owner, nameless_client, user2
    ):
        """The approved-proposal route builds its own invitation.

        `approve_proposal` calls `deliver_invitation` with the owner as inviter,
        separately from `CollectionInviteView` — so the direct invite being clean
        says nothing about this one, and line coverage says even less: this path
        was fully *executed* by the proposal tests while nothing asserted on the
        name it sent.
        """
        from core.models import InvitationProposal

        collection = Collection.objects.create(
            code="PRPCOL", owner=nameless_owner, headline="Tools"
        )
        collection.invites.add(user2)
        proposal = InvitationProposal.objects.create(
            collection=collection, proposer=user2, email="suggested@example.com"
        )
        mail.outbox.clear()

        res = nameless_client.post(f"/api/v1/proposals/{proposal.code}/approve/")
        assert res.status_code == 200
        assert mail.outbox, "the approved suggestion should have been invited"
        assert NAMELESS not in _bodies()

    def test_a_pending_invitation_does_not_name_the_owner_by_their_address(
        self, nameless_owner, authenticated_client2, user2
    ):
        """`/my-invitations/` is read by somebody who is only invited so far."""
        collection = Collection.objects.create(
            code="PNDCOL", owner=nameless_owner, headline="Tools"
        )
        RSVP.objects.create(
            user_code=user2,
            user_email=user2.email,
            action=RSVP.Action.COLLECTION_INVITE,
            target_code=collection.code,
        )

        res = authenticated_client2.get("/api/v1/my-invitations/")
        assert res.status_code == 200
        assert res.data[0]["owner_name"] != NAMELESS


@pytest.mark.django_db
class TestTheLenderIsNotIdentifiedByTheirAddress:
    def test_a_nameless_owners_decision_does_not_hand_over_their_address(
        self, nameless_owner, nameless_client, user2
    ):
        """The mirror of `MyBookingSerializer.owner_name`, which already
        withholds it — the decision notification must agree with the API the
        requester reads it next to."""
        thing = Thing.objects.create(code="BKTHNG", owner=nameless_owner, headline="Drill")
        booking = BookingPeriod.objects.create(
            code="BKG001",
            thing_code=thing,
            thing_type=thing.type,
            requester_code=user2,
            requester_email=user2.email,
            owner_code=nameless_owner,
        )
        mail.outbox.clear()

        res = nameless_client.post(f"/api/v1/bookings/{booking.code}/accept/", {}, format="json")
        assert res.status_code == 200

        assert NAMELESS not in _bodies()
        payload = InAppNotification.objects.get(user=user2, type="BOOKING_ACCEPTED").payload
        assert payload["owner_name"] != NAMELESS


@pytest.mark.django_db
class TestTheStandInSpeaksTheRecipientsLanguage:
    def test_the_stand_in_is_translated_per_recipient(self, settings):
        """The substitute is a word in the copy, so it follows the same language
        hierarchy every other word in the email does."""
        from core.services.email_service import _member_name

        assert _member_name("", "en") == "A member"
        assert _member_name("", "es") == "Un miembro"
        assert _member_name("", "ca") == "Un membre"

    def test_a_real_name_is_never_replaced(self):
        from core.services.email_service import _member_name

        assert _member_name("Lala", "es") == "Lala"

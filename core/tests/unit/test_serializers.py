"""
Unit tests for OIUEEI serializers.
"""

import pytest

from core.models import FAQ, Collection, Thing, User
from core.serializers import (
    CollectionCreateSerializer,
    CollectionSerializer,
    FAQCreateSerializer,
    FAQSerializer,
    RequestLinkSerializer,
    ThingCreateSerializer,
    ThingSerializer,
    UserPublicSerializer,
    UserSerializer,
)


class TestRequestLinkSerializer:
    """Tests for RequestLinkSerializer."""

    def test_valid_email(self):
        """Should accept valid email."""
        serializer = RequestLinkSerializer(data={"email": "test@example.com"})
        assert serializer.is_valid()
        assert serializer.validated_data["email"] == "test@example.com"

    def test_invalid_email(self):
        """Should reject invalid email."""
        serializer = RequestLinkSerializer(data={"email": "not-an-email"})
        assert not serializer.is_valid()
        assert "email" in serializer.errors


@pytest.mark.django_db
class TestUserSerializer:
    """Tests for UserSerializer."""

    def test_serialize_user(self):
        """Should serialize user with all fields."""
        user = User.objects.create(
            code="ABC123",
            email="test@example.com",
            name="Test User",
        )
        serializer = UserSerializer(user)
        data = serializer.data

        assert data["code"] == "ABC123"
        assert data["email"] == "test@example.com"
        assert data["name"] == "Test User"


@pytest.mark.django_db
class TestUserPublicSerializer:
    """Tests for UserPublicSerializer."""

    def test_serialize_public_user(self):
        """Should serialize only public fields."""
        user = User.objects.create(
            code="ABC123",
            email="test@example.com",
            name="Test User",
        )
        serializer = UserPublicSerializer(user)
        data = serializer.data

        assert data["code"] == "ABC123"
        assert data["name"] == "Test User"
        assert "email" not in data


@pytest.mark.django_db
class TestCollectionSerializer:
    """Tests for CollectionSerializer."""

    def test_serialize_collection(self):
        """Should serialize collection with all fields."""
        user = User.objects.create(code="ABC123", email="test@example.com")
        collection = Collection.objects.create(
            code="COLL01",
            owner=user,
            headline="My Collection",
        )
        serializer = CollectionSerializer(collection)
        data = serializer.data

        assert data["code"] == "COLL01"
        assert data["headline"] == "My Collection"
        assert "theeeme" not in data


class TestCollectionCreateSerializer:
    """Tests for CollectionCreateSerializer."""

    def test_valid_collection(self):
        """Should accept valid collection data (theeeme is optional)."""
        serializer = CollectionCreateSerializer(
            data={
                "headline": "My Collection",
            }
        )
        assert serializer.is_valid()

    def test_missing_headline(self):
        """Should reject missing headline."""
        serializer = CollectionCreateSerializer(data={})
        assert not serializer.is_valid()
        assert "headline" in serializer.errors


@pytest.mark.django_db
class TestThingSerializer:
    """Tests for ThingSerializer."""

    def test_serialize_thing(self):
        """Should serialize thing with all fields."""
        user = User.objects.create(code="ABC123", email="test@example.com")
        thing = Thing.objects.create(
            code="THNG01",
            owner=user,
            headline="My Thing",
            thumbnail="oiueei/things/pic1",
        )
        serializer = ThingSerializer(thing)
        data = serializer.data

        assert data["code"] == "THNG01"
        assert data["headline"] == "My Thing"
        assert "thumbnail_url" in data

    def test_owner_name_does_not_leak_email(self):
        """L2: owner_name uses the bare name, never the email fallback — it's
        shown to co-members, so a no-name owner must not expose their address."""
        owner = User.objects.create(code="NMLES1", email="nameless@example.com", name="")
        thing = Thing.objects.create(code="THNG09", owner=owner, headline="Y")
        data = ThingSerializer(thing).data
        assert data["owner_name"] == ""
        assert "nameless@example.com" not in str(data)

    def test_owner_email_fallback_only_for_collection_owner(self):
        """On the community grid a no-name thing owner's email is shown to the
        collection owner (who already sees co-members' emails) but never to other
        members or anonymous visitors (L2)."""
        from django.contrib.auth.models import AnonymousUser
        from rest_framework.test import APIRequestFactory

        owner = User.objects.create(code="GRDOWN", email="owner@example.com", name="Owner")
        nameless = User.objects.create(code="GHOST1", email="ghost@example.com", name="")
        collection = Collection.objects.create(
            code="GRID01",
            owner=owner,
            headline="Community",
            mode=Collection.Mode.COMMUNITY,
        )
        thing = Thing.objects.create(code="GTHNG1", owner=nameless, headline="Z")
        collection.things.add(thing)

        def owner_name_seen_by(viewer):
            request = APIRequestFactory().get("/")
            request.user = viewer
            data = CollectionSerializer(collection, context={"request": request}).data
            return data["things"][0]["owner_name"]

        # The collection owner gets the email fallback for a no-name owner.
        assert owner_name_seen_by(owner) == "ghost@example.com"
        # A different member never sees the email.
        other = User.objects.create(code="OTHER1", email="other@example.com", name="Other")
        assert owner_name_seen_by(other) == ""
        # Neither does an anonymous visitor (PUBLIC collections are public-readable).
        assert owner_name_seen_by(AnonymousUser()) == ""

    def test_serialize_thing_with_collection(self):
        """Should include collection_code and collection_headline."""
        user = User.objects.create(code="OWN001", email="owner@example.com")
        thing = Thing.objects.create(
            code="THNG02",
            owner=user,
            headline="Collected Thing",
        )
        collection = Collection.objects.create(
            code="COL001",
            owner=user,
            headline="My Collection",
        )
        collection.things.add(thing)

        serializer = ThingSerializer(thing)
        data = serializer.data

        assert data["collection_code"] == "COL001"
        assert data["collection_headline"] == "My Collection"

    def test_serialize_thing_without_collection(self):
        """Should return None for collection fields when thing has no collection."""
        user = User.objects.create(code="OWN002", email="owner2@example.com")
        thing = Thing.objects.create(
            code="THNG03",
            owner=user,
            headline="Orphan Thing",
        )

        serializer = ThingSerializer(thing)
        data = serializer.data

        assert data["collection_code"] is None
        assert data["collection_headline"] is None

    def test_pending_questions_excludes_hidden_faqs(self):
        """A question the owner hid is dealt with, not pending — the badge
        must not keep nagging about it forever."""
        owner = User.objects.create(code="PQOWN1", email="pqowner@example.com")
        questioner = User.objects.create(code="PQASK1", email="pqasker@example.com")
        thing = Thing.objects.create(code="PQTH01", owner=owner, headline="Pending Q")

        visible_unanswered = FAQ.objects.create(
            thing=thing, questioner=questioner, question="Visible?", answer=""
        )
        FAQ.objects.create(thing=thing, questioner=questioner, question="Answered?", answer="Yes")
        hidden_unanswered = FAQ.objects.create(
            thing=thing,
            questioner=questioner,
            question="Hidden?",
            answer="",
            is_visible=False,
        )

        assert ThingSerializer(thing).data["pending_questions"] == 1

        # Showing the hidden one again restores it to the count.
        hidden_unanswered.is_visible = True
        hidden_unanswered.save()
        assert ThingSerializer(thing).data["pending_questions"] == 2

        # Hiding the other unanswered one drops it back out.
        visible_unanswered.is_visible = False
        visible_unanswered.save()
        assert ThingSerializer(thing).data["pending_questions"] == 1


class TestThingCreateSerializer:
    """Tests for ThingCreateSerializer."""

    def test_valid_thing(self):
        """Should accept valid thing data."""
        serializer = ThingCreateSerializer(
            data={
                "headline": "My Thing",
                "type": "GIFT_THING",
            }
        )
        assert serializer.is_valid()

    def test_missing_headline(self):
        """Should reject missing headline."""
        serializer = ThingCreateSerializer(data={"type": "GIFT_THING"})
        assert not serializer.is_valid()

    def test_valid_with_detail_fields(self):
        """Should accept availability, location, and condition."""
        serializer = ThingCreateSerializer(
            data={
                "headline": "My Thing",
                "type": "GIFT_THING",
                "availability": "IMMEDIATE",
                "location": "Helsinki",
                "condition": "GOOD",
            }
        )
        assert serializer.is_valid()

    def test_location_max_length(self):
        """Should reject location exceeding 32 characters."""
        serializer = ThingCreateSerializer(
            data={
                "headline": "My Thing",
                "type": "GIFT_THING",
                "location": "A" * 33,
            }
        )
        assert not serializer.is_valid()
        assert "location" in serializer.errors

    def test_location_rejects_html(self):
        """Should reject HTML tags in location."""
        serializer = ThingCreateSerializer(
            data={
                "headline": "My Thing",
                "type": "GIFT_THING",
                "location": "<script>alert(1)</script>",
            }
        )
        assert not serializer.is_valid()
        assert "location" in serializer.errors


@pytest.mark.django_db
class TestFAQSerializer:
    """Tests for FAQSerializer."""

    def _faq(self):
        owner = User.objects.create(code="OWNER1", email="owner@example.com")
        thing = Thing.objects.create(code="THNG01", owner=owner, headline="Thing")
        questioner = User.objects.create(code="USR001", email="usr001@example.com", name="Ana")
        return FAQ.objects.create(
            code="FAQ001",
            thing=thing,
            questioner=questioner,
            question="Is this available?",
            answer="Yes!",
        )

    def test_serialize_faq(self):
        """Should serialize FAQ with all fields."""
        from rest_framework.test import APIRequestFactory

        faq = self._faq()
        request = APIRequestFactory().get("/")
        request.user = faq.questioner
        data = FAQSerializer(faq, context={"request": request}).data

        assert data["code"] == "FAQ001"
        assert data["question"] == "Is this available?"
        assert data["answer"] == "Yes!"
        assert data["questioner_name"] == "Ana"

    def test_asker_name_is_withheld_from_a_reader_who_is_not_signed_in(self):
        """A thing in a PUBLIC collection is readable with no account, and the
        member who asked published nothing — so the name goes only to signed-in
        readers (the rule `CollectionSerializer.get_invites` already applies to
        the member list). Request-less use withholds too: fail closed, so a call
        site that forgets the context cannot leak."""
        from django.contrib.auth.models import AnonymousUser
        from rest_framework.test import APIRequestFactory

        faq = self._faq()

        anonymous = APIRequestFactory().get("/")
        anonymous.user = AnonymousUser()
        assert FAQSerializer(faq, context={"request": anonymous}).data["questioner_name"] == ""
        assert FAQSerializer(faq).data["questioner_name"] == ""

        # The question itself is still public — it is only the asker who isn't.
        assert FAQSerializer(faq).data["question"] == "Is this available?"


class TestFAQCreateSerializer:
    """Tests for FAQCreateSerializer."""

    def test_valid_faq(self):
        """Should accept valid FAQ data."""
        serializer = FAQCreateSerializer(data={"question": "Is this available?"})
        assert serializer.is_valid()

    def test_missing_question(self):
        """Should reject missing question."""
        serializer = FAQCreateSerializer(data={})
        assert not serializer.is_valid()


class TestInputBounds:
    """L7: numeric/date input bounds on thing fee and booking dates."""

    def test_negative_fee_rejected(self):
        serializer = ThingCreateSerializer(
            data={"type": "SELL_THING", "headline": "X", "fee": "-5.00"}
        )
        assert not serializer.is_valid()
        assert "fee" in serializer.errors

    def test_dates_beyond_three_months_rejected(self):
        from datetime import date, timedelta

        from core.serializers.booking import ThingRequestWithDatesSerializer

        far = date.today() + timedelta(days=120)
        serializer = ThingRequestWithDatesSerializer(
            data={"start_date": str(date.today()), "end_date": str(far)}
        )
        assert not serializer.is_valid()
        assert "end_date" in serializer.errors

    def test_dates_within_three_months_accepted(self):
        from datetime import date, timedelta

        from core.serializers.booking import ThingRequestWithDatesSerializer

        soon = date.today() + timedelta(days=30)
        serializer = ThingRequestWithDatesSerializer(
            data={"start_date": str(date.today()), "end_date": str(soon)}
        )
        assert serializer.is_valid()

    def test_past_start_date_rejected(self):
        """A pickup cannot start in the past — otherwise a backdated booking
        would block days that already happened."""
        from datetime import date, timedelta

        from core.serializers.booking import ThingRequestWithDatesSerializer

        yesterday = date.today() - timedelta(days=1)
        serializer = ThingRequestWithDatesSerializer(
            data={"start_date": str(yesterday), "end_date": str(date.today())}
        )
        assert not serializer.is_valid()
        assert "start_date" in serializer.errors

    def test_end_before_start_rejected(self):
        """A return before the pickup is not a date range."""
        from datetime import date, timedelta

        from core.serializers.booking import ThingRequestWithDatesSerializer

        serializer = ThingRequestWithDatesSerializer(
            data={
                "start_date": str(date.today() + timedelta(days=5)),
                "end_date": str(date.today() + timedelta(days=2)),
            }
        )
        assert not serializer.is_valid()
        assert "end_date" in serializer.errors


@pytest.mark.django_db
class TestCoMemberNameLeak:
    """L2: serializers shown to a co-member must use the bare name, never the
    display_name email fallback. Locks in the Must-Have fix for the two
    serializers that previously used display_name."""

    def test_my_booking_owner_name_does_not_leak_email(self):
        """MyBookingSerializer.owner_name is the bare owner name — a no-name
        owner's email must not reach the requester."""
        from core.models.booking import BookingPeriod
        from core.serializers import MyBookingSerializer

        owner = User.objects.create(code="OWNNML", email="owner-nameless@example.com", name="")
        requester = User.objects.create(code="REQ001", email="req@example.com", name="Req")
        thing = Thing.objects.create(code="BTH001", owner=owner, headline="Lent thing")
        booking = BookingPeriod.objects.create(
            thing_code=thing,
            thing_type=thing.type,
            requester_code=requester,
            requester_email=requester.email,
            owner_code=owner,
        )

        data = MyBookingSerializer(booking).data
        assert data["owner_name"] == ""
        assert "owner-nameless@example.com" not in str(data)


@pytest.mark.django_db
class TestJourneyNamesFailClosed:
    """The journey withholds member names when there is no request to judge.

    `_may_read_names` treats a missing request as "not signed in", so an
    internal or request-less caller gets the same empty values an anonymous
    reader does. Every other test of this reaches the serializer *through the
    view*, which always supplies a request — so nothing pinned the one branch
    the docstring actually promises.

    That gap is invisible in the worst way. Rewriting the guard as
    `return not request or request.user.is_authenticated` — an inversion that
    reads like a tidy-up — would leave all 1155 tests green and quietly hand
    every name back to any caller that forgot the context. The FAQ twin is
    pinned this way in `TestFAQSerializer`; this is the other half.
    """

    def _stats(self, from_user, to_user):
        from core.models.transfer import ThingTransfer
        from core.serializers.transfer import ThingTransferStatsSerializer

        thing = Thing.objects.create(code="JTH001", owner=from_user, headline="A drill")
        transfer = ThingTransfer.objects.create(
            code="JTR001",
            thing=thing,
            from_user=from_user,
            to_user=to_user,
            lent_date="2026-01-01",
        )
        # The shape the view builds, minus the context — which is the point.
        return ThingTransferStatsSerializer(
            {
                "total_transfers": 1,
                "unique_homes": 2,
                "current_holder": to_user.code,
                "current_holder_name": to_user.name,
                "original_owner": from_user.code,
                "original_owner_name": from_user.name,
                "transfers": [transfer],
            }
        ).data

    def test_a_serializer_with_no_request_names_nobody(self):
        lender = User.objects.create(code="JLEND1", email="lender@example.com", name="Lila")
        borrower = User.objects.create(code="JBORR1", email="borrower@example.com", name="Bea")

        data = self._stats(lender, borrower)

        assert data["current_holder_name"] is None
        assert data["original_owner_name"] is None
        assert data["transfers"][0]["from_user_name"] == ""
        assert data["transfers"][0]["to_user_name"] == ""
        assert "Lila" not in str(data)
        assert "Bea" not in str(data)

    def test_the_journey_itself_still_comes_through(self):
        """Withholding the people must not withhold the story — the counts and
        the codes are what the public journey is for."""
        lender = User.objects.create(code="JLEND2", email="lender2@example.com", name="Lila")
        borrower = User.objects.create(code="JBORR2", email="borrower2@example.com", name="Bea")

        data = self._stats(lender, borrower)

        assert data["total_transfers"] == 1
        assert data["unique_homes"] == 2
        assert data["current_holder"] == "JBORR2"
        assert data["transfers"][0]["lent_date"] == "2026-01-01"

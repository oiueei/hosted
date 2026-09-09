"""
FAQ views for OIUEEI.
"""

from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django_ratelimit.decorators import ratelimit
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import FAQ, Thing
from core.models.event import Event
from core.models.notification import InAppNotification
from core.pagination import StandardResultsPagination
from core.serializers import FAQAnswerSerializer, FAQCreateSerializer, FAQSerializer
from core.services.email_service import (
    send_faq_answer_email,
    send_faq_hide_email,
    send_faq_question_email,
)
from core.views._helpers import deny_if_cannot_view, viewer_code


class ThingFAQListView(APIView):
    """
    GET /api/v1/things/{thing_code}/faq/
    List FAQs for a thing.

    POST /api/v1/things/{thing_code}/faq/
    Ask a question about a thing.
    """

    def get_permissions(self):
        # Listing questions (GET) is part of the public "social layer" — anyone
        # who can view the thing may read them. Asking a question (POST) needs auth.
        if self.request.method == "POST":
            return [IsAuthenticated()]
        return [AllowAny()]

    def get_thing(self, thing_code):
        return get_object_or_404(Thing, code=thing_code)

    def get(self, request, thing_code):
        thing = self.get_thing(thing_code)
        viewer = viewer_code(request)

        denied = deny_if_cannot_view(thing, viewer, "Not authorized to view this thing's FAQs")
        if denied:
            return denied

        # Get visible FAQs (or all for a manager — the owner, or a PROPRIETARY
        # collection's curator, who runs its FAQs)
        if thing.can_manage(viewer):
            faqs = FAQ.objects.filter(thing=thing).select_related("questioner").order_by("-created")
        else:
            faqs = (
                FAQ.objects.filter(thing=thing, is_visible=True)
                .select_related("questioner")
                .order_by("-created")
            )

        paginator = StandardResultsPagination()
        page = paginator.paginate_queryset(faqs, request)
        if page is not None:
            serializer = FAQSerializer(page, many=True, context={"request": request})
            return paginator.get_paginated_response(serializer.data)

        serializer = FAQSerializer(faqs, many=True, context={"request": request})
        return Response(serializer.data)

    @method_decorator(ratelimit(key="user", rate="20/h", method="POST", block=True))
    def post(self, request, thing_code):
        thing = self.get_thing(thing_code)

        # A manager cannot ask questions about a thing they run — the owner, or
        # a curator of a PROPRIETARY collection it sits in (they answer, they
        # don't ask).
        if thing.can_manage(request.user.code):
            return Response(
                {"error": "Owner cannot ask questions about their own thing"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        denied = deny_if_cannot_view(
            thing, request.user.code, "Not authorized to ask questions about this thing"
        )
        if denied:
            return denied

        serializer = FAQCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        faq = FAQ.objects.create(
            thing=thing,
            questioner=request.user,
            question=serializer.validated_data["question"],
        )
        Event.log(Event.Kind.FAQ_ASKED, actor=request.user, thing=thing)

        # Notify every manager — the thing owner, and the curators of a
        # PROPRIETARY collection it sits in, who answer questions shoulder to
        # shoulder with the founder. In COMMUNITY that set is just the owner (a
        # member owns what they contribute). Bare name only: nothing in the FAQ
        # API ever hands a co-member the asker's address, and this must not be
        # the one thing that does.
        questioner_name = request.user.name
        for manager in thing.managers():
            if manager.code == request.user.code:
                continue
            if manager.email:
                send_faq_question_email(questioner_name, thing, faq.question, manager.email)
            InAppNotification.objects.create(
                user=manager,
                type=InAppNotification.Type.FAQ_QUESTION,
                payload={"thing_headline": thing.headline, "questioner_name": questioner_name},
            )

        return Response(
            FAQSerializer(faq, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class FAQDetailView(APIView):
    """
    GET /api/v1/faq/{faq_code}/
    View a FAQ.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, faq_code):
        faq = get_object_or_404(FAQ.objects.select_related("questioner", "thing"), code=faq_code)

        # Get the thing to check access
        thing = faq.thing

        denied = deny_if_cannot_view(thing, request.user.code, "Not authorized to view this FAQ")
        if denied:
            return denied

        # Check visibility for non-owners
        if not faq.is_visible:
            # Only a manager of the thing or the questioner can see hidden FAQs
            if not thing.can_manage(request.user.code) and faq.questioner_id != request.user.code:
                return Response(
                    {"error": "FAQ not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

        serializer = FAQSerializer(faq, context={"request": request})
        return Response(serializer.data)


class FAQAnswerView(APIView):
    """
    POST /api/v1/faq/{faq_code}/answer/
    Answer a FAQ (a manager of the thing — its owner, or a PROPRIETARY
    collection's curator).
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, faq_code):
        faq = get_object_or_404(FAQ.objects.select_related("questioner", "thing"), code=faq_code)

        thing = faq.thing

        if not thing.can_manage(request.user.code):
            return Response(
                {"error": "Only the thing owner can answer questions"},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = FAQAnswerSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        faq.set_answer(serializer.validated_data["answer"])

        # Notify questioner by email and in-app
        questioner = faq.questioner
        if questioner and questioner.email:
            owner_name = request.user.name  # bare name (L2)
            send_faq_answer_email(owner_name, thing, faq.question, faq.answer, questioner.email)
            InAppNotification.objects.create(
                user=questioner,
                type=InAppNotification.Type.FAQ_ANSWERED,
                payload={"thing_headline": thing.headline, "owner_name": owner_name},
            )

        return Response(FAQSerializer(faq, context={"request": request}).data)


class FAQVisibilityView(APIView):
    """
    POST /api/v1/faq/{faq_code}/hide/
    Hide a FAQ (a manager of the thing).

    POST /api/v1/faq/{faq_code}/show/
    Show a FAQ (a manager of the thing).
    """

    permission_classes = [IsAuthenticated]

    def _get_faq_and_thing(self, faq_code):
        faq = get_object_or_404(FAQ.objects.select_related("questioner", "thing"), code=faq_code)
        return faq, faq.thing

    def post(self, request, faq_code, action):
        faq, thing = self._get_faq_and_thing(faq_code)

        if not thing.can_manage(request.user.code):
            return Response(
                {"error": "Only the thing owner can change FAQ visibility"},
                status=status.HTTP_403_FORBIDDEN,
            )

        if action == "hide":
            faq.is_visible = False
            faq.save(update_fields=["is_visible"])

            # Notify questioner by email and in-app
            questioner = faq.questioner
            if questioner and questioner.email:
                owner_name = request.user.name  # bare name (L2)
                send_faq_hide_email(owner_name, thing, faq.question, questioner.email)
                InAppNotification.objects.create(
                    user=questioner,
                    type=InAppNotification.Type.FAQ_HIDDEN,
                    payload={"thing_headline": thing.headline, "owner_name": owner_name},
                )

            return Response(
                {
                    "message": "FAQ hidden",
                    "faq": FAQSerializer(faq, context={"request": request}).data,
                }
            )
        elif action == "show":
            faq.is_visible = True
            faq.save(update_fields=["is_visible"])
            return Response(
                {
                    "message": "FAQ shown",
                    "faq": FAQSerializer(faq, context={"request": request}).data,
                }
            )
        else:
            return Response(
                {"error": "Invalid action"},
                status=status.HTTP_400_BAD_REQUEST,
            )

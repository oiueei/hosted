"""The open door of a hosted OIUEEI.

Upstream there is none: an account exists because somebody chose to admit a
specific person, and `POST /auth/join/` creates nothing without a share token or
a public collection's code. That is the right default for software people
self-host — and the wrong one for a service that wants strangers to be able to
walk in and look around.

So this view is the operator's answer, and it lives here because it *is* the
operator's answer. It is deliberately the thing the standalone refuses to be: an
endpoint that takes an email and returns an account.

Mounted at the historical `/api/v1/auth/pop-in/` (see `urls.py`) so the links
already in the world keep working.
"""

import logging

from django.conf import settings
from django.utils.decorators import method_decorator
from django_ratelimit.decorators import ratelimit
from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.renderers import TemplateHTMLRenderer
from rest_framework.response import Response
from rest_framework.settings import api_settings
from rest_framework.views import APIView

from core.models import RSVP, Collection, Language, User
from core.models.event import Event
from core.serializers import RequestLinkSerializer
from core.utils import get_client_ip, redact_email

# Imported, never copied. The join side effects — the idempotent membership add,
# the first-join MEMBER_JOINED event, the welcome PDF, the capacity alarm — are
# product behaviour and must stay identical whichever door someone came through;
# a second implementation here would drift within a release. The dependency runs
# in the only direction that is safe: the service layer depends on the product.
from core.views.auth import _join_collection, _send_magic_link, email_ratelimit_key

from .emails import send_creator_validation_request_email
from .forms import RequestAccessForm
from .models import CreatorValidation

security_logger = logging.getLogger("security")


class PopInView(APIView):
    """
    POST /api/v1/auth/pop-in/

    Creates the account on the spot and joins it to every `is_onboarding`
    collection, then emails a magic link. No prior invitation, no token.

    A `share_token` or a `collection_code` is still honoured, and takes
    precedence: someone arriving with a specific collection in hand joins that
    one. Those two paths are product, so they are delegated to `JoinView` rather
    than reimplemented — this view only owns the case upstream refuses, which is
    the case with no target at all.
    """

    permission_classes = [AllowAny]

    @method_decorator(ratelimit(key="ip", rate="5/m", method="POST", block=True))
    @method_decorator(ratelimit(key=email_ratelimit_key, rate="5/h", method="POST", block=True))
    def post(self, request):
        # Local import: `JoinView` is a view class, and importing it at module
        # level would tie this module's import order to `core.urls`.
        from core.views.auth import JoinView

        serializer = RequestLinkSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"].lower()
        share_token = (request.data.get("share_token") or "").strip() or None
        collection_code = (request.data.get("collection_code") or "").strip() or None

        # Pointed at a specific collection? That is the product's path, verbatim.
        target, _source = JoinView._resolve_target(share_token, collection_code)
        if target is not None:
            return JoinView.as_view()(request._request)

        return self._open_door(request, email)

    def _open_door(self, request, email):
        """Create the account and put it in the demo collections.

        The part that only makes sense on a service someone is running for
        strangers, and the reason this app exists.
        """
        ip = get_client_ip(request)
        language = (request.data.get("language") or "").strip().lower()
        if language not in Language.values:
            language = ""

        onboarding_collections = list(Collection.objects.filter(is_onboarding=True))

        user, created = User.objects.get_or_create(email=email)
        if created:
            if language:
                user.language = language
                user.save(update_fields=["language"])
            Event.log(Event.Kind.USER_JOINED, actor=user)

        for collection in onboarding_collections:
            _join_collection(collection, user, source=Event.Source.ONBOARDING)

        # No `target_code`: they came to look around, not to reach one group, so
        # verifying the link lands them on the welcome page rather than dropping
        # them into a collection. `origin=POPIN` is what tells VerifyLinkView so.
        rsvp = RSVP.objects.create(
            user_code=user,
            user_email=email,
            origin=RSVP.Origin.POPIN,
        )
        magic_link_base = getattr(settings, "MAGIC_LINK_BASE_URL", "http://localhost:3000/verify")
        _send_magic_link(email, f"{magic_link_base}/{rsvp.token}", user=user)

        security_logger.info(
            f"Pop-in request for {redact_email(email)} from IP {ip} "
            f"(new_user={created}, onboarding_collections={len(onboarding_collections)})"
        )

        # Byte-identical to `JoinView`'s, and it has to stay that way: the two
        # views answer the same URL space, and a visitor must not be able to tell
        # which one handled their request — nor, on this one, whether the address
        # already had an account.
        return Response(
            {"message": "Check your email — we've sent you a magic link to join OIUEEI."},
            status=status.HTTP_200_OK,
        )


class RequestAccessView(APIView):
    """
    GET / POST `/request-access/`

    The form somebody fills in to be allowed to run a COMMUNITY collection, or
    to lend and rent. A plain Django page, not part of the SPA: it is this
    deployment's own conversation with a person, it is read once, and putting it
    in the React bundle would mean every visitor downloads a form almost nobody
    fills in.

    It is a DRF view rather than a Django one for a single reason: the session
    is a **JWT cookie**, which only `CookieJWTAuthentication` resolves. A plain
    `django.views.View` would see `AnonymousUser` for someone who is perfectly
    well logged in.
    """

    permission_classes = [AllowAny]
    authentication_classes = api_settings.DEFAULT_AUTHENTICATION_CLASSES
    # The browser posts a real HTML form; the project default parses JSON only.
    parser_classes = [FormParser, MultiPartParser]
    renderer_classes = [TemplateHTMLRenderer]
    template_name = "hosted/request_access.html"

    def get(self, request):
        if not request.user.is_authenticated:
            return Response({"needs_login": True})

        validation = self._existing(request.user)
        return Response(
            {
                "validation": validation,
                # A refused request can be made again: the answer was about what
                # was said, and somebody may have more to say. Approved is the
                # one state with nothing left to ask.
                "form": None if validation and validation.is_approved else RequestAccessForm(),
            }
        )

    @method_decorator(ratelimit(key="user_or_ip", rate="5/h", method="POST", block=True))
    def post(self, request):
        if not request.user.is_authenticated:
            return Response({"needs_login": True}, status=status.HTTP_403_FORBIDDEN)

        validation = self._existing(request.user)
        if validation and validation.is_approved:
            return Response({"validation": validation, "form": None})

        form = RequestAccessForm(request.data, instance=validation)
        if not form.is_valid():
            return Response(
                {"form": form, "validation": validation}, status=status.HTTP_400_BAD_REQUEST
            )

        # One row per person, reset to PENDING: asking again after a "no" is the
        # same conversation continued, not a second file opened.
        submitted = form.save(commit=False)
        submitted.user = request.user
        submitted.status = CreatorValidation.Status.PENDING
        submitted.resolved = None
        submitted.save()

        security_logger.info(f"Creator validation requested by {request.user.code}")
        # The operator is told, because nobody reads a table on the off chance.
        # `_send` swallows its own failures, so a mail server having a bad
        # afternoon cannot lose the request that is already saved above.
        send_creator_validation_request_email(submitted)
        return Response({"validation": submitted, "just_sent": True, "form": None})

    @staticmethod
    def _existing(user):
        return CreatorValidation.objects.filter(user=user).first()

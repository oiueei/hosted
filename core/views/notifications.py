"""
Notification preferences views for OIUEEI.

Two endpoints:
- Authenticated PATCH/GET via /auth/me/ and /users/{code}/ (handled by existing views).
- Token-based GET/PATCH at /notifications/token/{token}/ so users can change
  preferences via the footer link in any email without needing to log in.
"""

from django.utils.decorators import method_decorator
from django_ratelimit.decorators import ratelimit
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import Collection, User
from core.services.email_service import verify_digest_mute_token, verify_notifications_token


class NotificationPrefsSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["notify_activity", "notify_news"]


class NotificationsByTokenView(APIView):
    """
    GET  /api/v1/notifications/token/{token}/
    PATCH /api/v1/notifications/token/{token}/

    Token-scoped endpoint for editing notify_activity / notify_news without login.
    Token is a TimestampSigner-signed user_code with a 1-year TTL
    (see core.services.email_service.make_notifications_token).
    """

    permission_classes = [AllowAny]

    def _resolve(self, token):
        user_code = verify_notifications_token(token)
        if not user_code:
            return None
        return User.objects.filter(code=user_code).first()

    @method_decorator(ratelimit(key="ip", rate="20/m", method="GET", block=True))
    def get(self, request, token):
        user = self._resolve(token)
        if not user:
            return Response(
                {"detail": "Invalid or expired link"},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        return Response(NotificationPrefsSerializer(user).data)

    @method_decorator(ratelimit(key="ip", rate="10/m", method="PATCH", block=True))
    def patch(self, request, token):
        user = self._resolve(token)
        if not user:
            return Response(
                {"detail": "Invalid or expired link"},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        serializer = NotificationPrefsSerializer(user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class DigestMuteByTokenView(APIView):
    """
    POST /api/v1/digest/mute/{token}/

    The one-click unsubscribe at the foot of every digest: silences that one
    collection's summaries for that one member, no login required. The token is
    a signed ``{user_code}:{collection_code}`` (see ``make_digest_mute_token``).

    **POST, not GET, on purpose** — same reasoning as the booking decisions in
    `VerifyLinkView`: a mail client's link scanner or a prefetch issues a bare
    GET and runs no JS, so it must not be able to unsubscribe someone. The SPA
    page fires this POST from JS, which a scanner never reaches.

    Idempotent, and it never reports whether the member was subscribed — the
    answer to "stop these" is always the same, and a token holder learns nothing
    about the account behind it.
    """

    permission_classes = [AllowAny]

    @method_decorator(ratelimit(key="ip", rate="10/m", method="POST", block=True))
    def post(self, request, token):
        resolved = verify_digest_mute_token(token)
        if not resolved:
            return Response(
                {"detail": "Invalid or expired link"},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        user_code, collection_code = resolved
        user = User.objects.filter(code=user_code).first()
        collection = Collection.objects.filter(code=collection_code).first()
        if not user or not collection:
            return Response(
                {"detail": "Invalid or expired link"},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        collection.digest_muted.add(user)
        return Response({"muted": True, "collection_headline": collection.headline})

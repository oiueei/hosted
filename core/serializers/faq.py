"""
FAQ serializers for OIUEEI.
"""

from rest_framework import serializers

from core.models import FAQ
from core.validators import SafeHeadlineField, SafeTextField


class FAQSerializer(serializers.ModelSerializer):
    """Full FAQ serializer."""

    thing = serializers.CharField(source="thing_id")
    questioner = serializers.CharField(source="questioner_id", allow_null=True)
    questioner_name = serializers.SerializerMethodField()

    class Meta:
        model = FAQ
        fields = [
            "code",
            "thing",
            "created",
            "questioner",
            "questioner_name",
            "question",
            "answer",
            "is_visible",
        ]
        read_only_fields = [
            "code",
            "thing",
            "created",
            "questioner",
        ]

    def get_questioner_name(self, obj):
        # Withheld from a reader who is not signed in. A thing sitting in a
        # PUBLIC collection is readable with no account at all, and the person
        # who asked the question is a third party who published nothing — unlike
        # the thing's owner, who chose to. `CollectionSerializer.get_invites`
        # already made this call for a group's member list ("real names of a
        # group's members don't belong to the open web"); these are the same
        # people, reached through a different endpoint.
        #
        # Fail-closed on a missing request, exactly like that method: a call
        # site that forgets to pass the context withholds the name rather than
        # leaking it.
        request = self.context.get("request")
        if not (request and request.user.is_authenticated):
            return ""
        # A deleted account keeps its questions but sheds its name (right to
        # erasure — FAQ.questioner is SET_NULL); the frontend renders its own
        # "former member" label for the empty value.
        return obj.questioner.name if obj.questioner else ""


class FAQCreateSerializer(serializers.Serializer):
    """Serializer for creating a FAQ (asking a question)."""

    question = SafeHeadlineField(max_length=64)


class FAQAnswerSerializer(serializers.Serializer):
    """Serializer for answering a FAQ."""

    answer = SafeTextField(max_length=256)

"""A network asks for approval here, like a community, and the answer says so.

**Tests code that is not in the standalone** (see `test_hosted_popin.py` for why the
file sits here). A NETWORK puts several entities' lending under one roof, so it is what
this deployment reads a sentence about a person before handing out: an unapproved
account does not see the mode, the API refuses it and says where to ask, and an approved
one gets it together with the rest of the product. The approval email names it in the
three languages.
"""

import pytest
from django.core import mail
from rest_framework import status

from core.models import Collection
from core.services.creator_policy import capabilities_for
from hosted import email_texts
from hosted.models import CreatorValidation
from hosted.policy import OPEN_MODES
from hosted.tally import REQUEST_ACCESS


@pytest.fixture(autouse=True)
def hosted_policy(settings):
    settings.CREATOR_POLICY = "hosted.policy.HostedCreatorPolicy"


def a_network(client):
    return client.post(
        "/api/v1/collections/",
        {
            "headline": "Xarxa del barri",
            "mode": "NETWORK",
            "kind": "LIBRARY",
            "allowed_thing_types": ["LEND_THING", "RENT_THING"],
        },
        format="json",
    )


@pytest.mark.django_db
class TestWhoMayOpenANetwork:
    def test_it_is_not_among_the_modes_anybody_has(self):
        assert Collection.Mode.NETWORK not in OPEN_MODES

    def test_an_account_not_approved_does_not_see_the_mode(self, user):
        assert Collection.Mode.NETWORK not in capabilities_for(user).collection_modes

    def test_an_account_not_approved_is_refused_and_told_where_to_ask(
        self, authenticated_client, user
    ):
        res = a_network(authenticated_client)

        assert res.status_code == status.HTTP_403_FORBIDDEN
        assert REQUEST_ACCESS["es"] in str(res.data)
        assert not Collection.objects.filter(mode=Collection.Mode.NETWORK).exists()

    def test_an_approved_account_has_it_with_the_rest_of_the_product(
        self, authenticated_client, user
    ):
        CreatorValidation.objects.create(user=user, who="x" * 25, intent="y" * 25).resolve(
            CreatorValidation.Status.APPROVED
        )

        assert Collection.Mode.NETWORK in capabilities_for(user).collection_modes
        assert a_network(authenticated_client).status_code == status.HTTP_201_CREATED

    def test_a_rejected_account_keeps_the_open_half_and_still_no_network(
        self, authenticated_client, user
    ):
        CreatorValidation.objects.create(user=user, who="x" * 25, intent="y" * 25).resolve(
            CreatorValidation.Status.REJECTED
        )

        assert a_network(authenticated_client).status_code == status.HTTP_403_FORBIDDEN


class TestTheWordsThatNameIt:
    """The approval email lists what opens; a network is one of the things."""

    @pytest.mark.parametrize(
        ("lang", "word"), [("en", "network"), ("es", "redes"), ("ca", "xarxes")]
    )
    def test_the_approval_names_networks_in_each_language(self, lang, word):
        texts = email_texts.TEXTS[lang]

        assert word in texts["approved_body"]
        assert word in texts["approved_plain"]

    @pytest.mark.django_db
    def test_the_email_the_operator_sends_says_it(self, user):
        from hosted.emails import send_creator_validation_decision_email

        user.language = "ca"
        user.save(update_fields=["language"])
        row = CreatorValidation.objects.create(
            user=user, who="x" * 25, intent="y" * 25, status=CreatorValidation.Status.APPROVED
        )
        mail.outbox.clear()

        send_creator_validation_decision_email(row)

        assert "xarxes" in mail.outbox[0].body

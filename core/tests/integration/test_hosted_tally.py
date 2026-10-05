"""Where "Request access" lives: three forms on Tally (`hosted/tally.py`).

**Tests code that is not in the standalone** (see `test_hosted_popin.py` for why the
file sits here).

It was a Django page of our own, `/request-access/`; CA moved it to Tally (2026-10-05),
one form per language, opened in a new tab. The SPA knows the addresses through its own
`externalForms.requestAccess`; the **server** needs them in three places the SPA does not
render, and each is pinned here in the language of whoever it is for:

- `capabilities.request_url` (what the approval notice falls back to);
- the two 403 bodies that say where to ask (a collection mode and a thing type that are
  not open yet) — core builds them from that very value;
- the email that tells somebody their request was not approved.

And the two copies of the addresses (this module's and `frontend/src/deployment/index.js`)
are read side by side so they cannot come apart.
"""

import re
from pathlib import Path

import pytest
from django.contrib.auth.models import AnonymousUser
from django.core import mail
from django.urls import NoReverseMatch, reverse
from rest_framework import status

from core.services.email_service import resolve_email_language
from hosted.emails import send_creator_validation_decision_email
from hosted.models import CreatorValidation
from hosted.policy import HostedCreatorPolicy
from hosted.tally import DEFAULT_LANGUAGE, REQUEST_ACCESS, request_access_url

POLICY = "hosted.policy.HostedCreatorPolicy"
ES, CA, EN = (REQUEST_ACCESS[lang] for lang in ("es", "ca", "en"))
ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(autouse=True)
def hosted_policy(settings):
    settings.CREATOR_POLICY = POLICY


def speaking(user, language):
    user.language = language
    user.save(update_fields=["language"])
    return user


class TestTheAddress:
    @pytest.mark.parametrize(
        ("language", "expected"),
        [
            ("es", "https://tally.so/r/zxaY4M"),
            ("ca", "https://tally.so/r/D4lz9N"),
            ("en", "https://tally.so/r/aQ8dPX"),
        ],
    )
    def test_each_language_has_its_own_form(self, language, expected):
        assert request_access_url(language) == expected

    @pytest.mark.parametrize("language", [None, "", "fr", "ES", "es-ES", "xx", 0])
    def test_blank_or_unknown_is_the_spanish_one_and_never_an_error(self, language):
        assert request_access_url(language) == ES

    def test_with_no_argument_it_is_the_spanish_one(self):
        assert request_access_url() == ES
        assert DEFAULT_LANGUAGE == "es"

    def test_they_are_three_different_bare_tally_forms(self):
        assert set(REQUEST_ACCESS) == {"es", "ca", "en"}
        for url in REQUEST_ACCESS.values():
            # Exactly as given, with nothing about the person added.
            assert re.fullmatch(r"https://tally\.so/r/[A-Za-z0-9]+", url)
        assert len(set(REQUEST_ACCESS.values())) == 3


class TestTheSameAddressesAsTheFrontend:
    def test_requestAccess_in_externalForms_is_this_module(self):  # noqa: N802
        source = (ROOT / "frontend" / "src" / "deployment" / "index.js").read_text()
        block = re.search(r"requestAccess:\s*\{(.*?)\}", source, re.DOTALL)
        assert block, "externalForms.requestAccess not found in deployment/index.js"

        written = dict(re.findall(r"(\w+):\s*'([^']+)'", block.group(1)))

        assert written == REQUEST_ACCESS


@pytest.mark.django_db
class TestCapabilitiesAndTheRefusals:
    @pytest.mark.parametrize(
        ("language", "expected"), [("es", ES), ("ca", CA), ("en", EN), ("", ES)]
    )
    def test_me_advertises_the_form_of_the_accounts_language(
        self, authenticated_client, user, language, expected
    ):
        speaking(user, language)

        capabilities = authenticated_client.get("/api/v1/auth/me/").data["capabilities"]

        assert capabilities["request_url"] == expected

    def test_an_anonymous_caller_gets_the_spanish_one_without_a_query(
        self, django_assert_num_queries
    ):
        with django_assert_num_queries(0):
            capabilities = HostedCreatorPolicy().capabilities(AnonymousUser())

        assert capabilities.request_url == ES

    def test_somebody_approved_has_nowhere_to_ask(self, authenticated_client, user):
        CreatorValidation.objects.create(
            user=speaking(user, "ca"),
            who="A neighbour",
            intent="A tool library",
            status=CreatorValidation.Status.APPROVED,
        )

        capabilities = authenticated_client.get("/api/v1/auth/me/").data["capabilities"]

        assert capabilities["request_url"] is None

    @pytest.mark.parametrize(("language", "expected"), [("es", ES), ("ca", CA), ("en", EN)])
    def test_the_403_for_a_collection_mode_names_the_form_of_their_language(
        self, authenticated_client, user, language, expected
    ):
        speaking(user, language)

        response = authenticated_client.post(
            "/api/v1/collections/", {"headline": "Mercadillo", "mode": "COMMUNITY"}, format="json"
        )

        body = str(response.data)
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert expected in body
        assert [url for url in REQUEST_ACCESS.values() if url != expected and url in body] == []

    @pytest.mark.parametrize(("language", "expected"), [("es", ES), ("ca", CA), ("en", EN)])
    def test_the_403_for_a_thing_type_names_the_form_of_their_language(
        self, authenticated_client, user, language, expected
    ):
        speaking(user, language)

        response = authenticated_client.post(
            "/api/v1/things/",
            {"type": "LEND_THING", "headline": "A ladder", "thumbnail": "img/x"},
            format="json",
        )

        body = str(response.data)
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert expected in body
        assert [url for url in REQUEST_ACCESS.values() if url != expected and url in body] == []

    def test_no_refusal_points_at_a_page_of_our_own_any_more(self, authenticated_client):
        response = authenticated_client.post(
            "/api/v1/collections/", {"headline": "Mercadillo", "mode": "COMMUNITY"}, format="json"
        )

        assert "/request-access" not in str(response.data)


@pytest.mark.django_db
class TestTheEmailThatSaysNo:
    def _refuse(self, user, language):
        speaking(user, language)
        validation = CreatorValidation.objects.create(
            user=user,
            who="Who",
            intent="Intent",
            status=CreatorValidation.Status.REJECTED,
        )
        send_creator_validation_decision_email(validation)
        return mail.outbox[-1]

    @pytest.mark.parametrize(("language", "expected"), [("es", ES), ("ca", CA), ("en", EN)])
    def test_it_links_the_form_of_the_language_it_is_written_in(self, user, language, expected):
        message = self._refuse(user, language)

        html = message.alternatives[0][0]
        for part in (message.body, html):
            assert expected in part
            assert [url for url in REQUEST_ACCESS.values() if url != expected and url in part] == []

    def test_with_no_language_set_it_is_the_form_of_the_language_it_falls_back_to(self, user):
        message = self._refuse(user, "")

        assert request_access_url(resolve_email_language(user=user)) in message.body

    def test_it_no_longer_links_a_page_of_our_own(self, user):
        message = self._refuse(user, "en")

        assert "/request-access" not in message.body

    def test_a_yes_still_goes_back_into_the_product(self, user):
        speaking(user, "ca")
        validation = CreatorValidation.objects.create(
            user=user, who="Who", intent="Intent", status=CreatorValidation.Status.APPROVED
        )

        send_creator_validation_decision_email(validation)

        body = mail.outbox[-1].body
        assert "/collections/new" in body
        assert "tally.so" not in body


@pytest.mark.django_db
class TestThePageOfOurOwnIsGone:
    def test_the_route_no_longer_exists(self):
        with pytest.raises(NoReverseMatch):
            reverse("hosted:request-access")

    def test_the_old_address_is_not_answered_by_a_form_of_ours(self, api_client):
        response = api_client.get("/request-access/")

        assert "Ask to run a group here" not in response.content.decode()
        # …nor does the slash-less typo redirect there any more.
        assert api_client.get("/request-access").status_code != status.HTTP_301_MOVED_PERMANENTLY

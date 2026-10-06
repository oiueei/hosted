"""Where "Request access" lives: three forms on Tally (`hosted/tally.py`).

**Tests code that is not in the standalone** (see `test_hosted_popin.py` for why the
file sits here).

It was a Django page of our own, `/request-access/`; it moved to Tally,
one form per language, opened in a new tab. The SPA knows the addresses through its own
`externalForms.requestAccess`; the **server** needs them in three places the SPA does not
render, and each is pinned here in the language of whoever it is for:

- `capabilities.request_url` (what the approval notice falls back to);
- the two 403 bodies that say where to ask (a collection mode and a thing type that are
  not open yet) — core builds them from that very value;
- the email that tells somebody their request was not approved;

and the old address of the page, `/request-access/` (and without the slash), which is out in
the world — in those emails, in bookmarks — and now redirects to the form of the visitor's
browser language.

And the two copies of the addresses (this module's and `frontend/src/deployment/index.js`)
are read side by side so they cannot come apart.

"Contact us" is covered the same way (`CONTACT`, `contact_url`), and so is `/contact`, a
page of core's whose address redirects to that form.
"""

import re
from pathlib import Path

import pytest
from django.contrib.auth.models import AnonymousUser
from django.core import mail
from django.test import RequestFactory
from django.urls import resolve
from rest_framework import status

from core.services.email_service import resolve_email_language
from hosted.emails import send_creator_validation_decision_email
from hosted.models import CreatorValidation
from hosted.policy import HostedCreatorPolicy
from hosted.tally import (
    CONTACT,
    DEFAULT_LANGUAGE,
    REQUEST_ACCESS,
    browser_language,
    contact_url,
    request_access_url,
)

POLICY = "hosted.policy.HostedCreatorPolicy"
ES, CA, EN = (REQUEST_ACCESS[lang] for lang in ("es", "ca", "en"))
CONTACT_ES, CONTACT_CA, CONTACT_EN = (CONTACT[lang] for lang in ("es", "ca", "en"))
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


class TestTheContactAddress:
    @pytest.mark.parametrize(
        ("language", "expected"),
        [
            ("es", "https://tally.so/r/PdaOy1"),
            ("ca", "https://tally.so/r/Gx2lye"),
            ("en", "https://tally.so/r/Y5LagN"),
        ],
    )
    def test_each_language_has_its_own_form(self, language, expected):
        assert contact_url(language) == expected

    @pytest.mark.parametrize("language", [None, "", "fr", "ES", "es-ES", "xx", 0])
    def test_blank_or_unknown_is_the_spanish_one_and_never_an_error(self, language):
        assert contact_url(language) == CONTACT_ES

    def test_with_no_argument_it_is_the_spanish_one(self):
        assert contact_url() == CONTACT_ES

    def test_they_are_three_different_bare_tally_forms(self):
        assert set(CONTACT) == {"es", "ca", "en"}
        for url in CONTACT.values():
            # Exactly as given, with nothing about the person added.
            assert re.fullmatch(r"https://tally\.so/r/[A-Za-z0-9]+", url)
        assert len(set(CONTACT.values())) == 3

    def test_it_is_not_the_request_access_form(self):
        """Two different forms: a request for access must not land in the contact inbox."""
        assert set(CONTACT.values()).isdisjoint(REQUEST_ACCESS.values())

    def test_it_speaks_the_languages_browser_language_chooses_from(self):
        """`browser_language` is written against one dictionary and serves both."""
        assert set(CONTACT) == set(REQUEST_ACCESS)


class TestTheSameAddressesAsTheFrontend:
    @pytest.mark.parametrize(
        ("form", "written_here"), [("requestAccess", REQUEST_ACCESS), ("contact", CONTACT)]
    )
    def test_each_form_in_externalForms_is_this_module(self, form, written_here):  # noqa: N802
        source = (ROOT / "frontend" / "src" / "deployment" / "index.js").read_text()
        block = re.search(rf"\b{form}:\s*\{{(.*?)\}}", source, re.DOTALL)
        assert block, f"externalForms.{form} not found in deployment/index.js"

        written = dict(re.findall(r"(\w+):\s*'([^']+)'", block.group(1)))

        assert written == written_here


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


class TestTheBrowsersLanguage:
    """`Accept-Language` → the form's language: the first the browser asks for that we
    have a form in, by its own order of preference, and `es` for anything else — not
    Django's `LANGUAGE_CODE` fallback (English), which `get_language_from_request` would
    give a visitor with no header at all."""

    @staticmethod
    def language(header=None):
        extra = {} if header is None else {"HTTP_ACCEPT_LANGUAGE": header}
        return browser_language(RequestFactory().get("/request-access/", **extra))

    @pytest.mark.parametrize(
        ("header", "expected"),
        [
            ("ca", "ca"),
            ("en", "en"),
            ("es", "es"),
            ("ca-ES,ca;q=0.9,en;q=0.8", "ca"),
            ("en-GB,en;q=0.9", "en"),
            ("EN-us", "en"),
            ("en;q=0.5, ca;q=0.9", "ca"),
            ("fr-FR,fr;q=0.9,en;q=0.5", "en"),
            ("de, it;q=0.9, ca;q=0.2", "ca"),
        ],
    )
    def test_the_first_of_ours_by_the_browsers_own_preference(self, header, expected):
        assert self.language(header) == expected

    @pytest.mark.parametrize(
        "header", [None, "", "fr", "fr-FR,fr;q=0.9", "*", "garbage;;;", "ca;q=zz"]
    )
    def test_none_of_ours_or_nothing_usable_is_the_spanish_one(self, header):
        assert self.language(header) == "es"


@pytest.mark.django_db
class TestTheOldAddressOfThePage:
    """The page is gone; its address redirects to the form.

    It was a Django page of ours (see the module docstring); without a route the address
    falls into the SPA's catch-all, where React Router reads it as the profile of a user
    called "request-access" and a broken profile page appears.
    """

    ADDRESSES = ["/request-access/", "/request-access"]

    @pytest.mark.parametrize("address", ADDRESSES)
    def test_it_redirects_with_a_302_and_not_a_permanent_move(self, api_client, address):
        response = api_client.get(address)

        assert response.status_code == status.HTTP_302_FOUND
        assert response.status_code != status.HTTP_301_MOVED_PERMANENTLY

    @pytest.mark.parametrize("address", ADDRESSES)
    def test_with_no_language_header_it_is_the_spanish_form(self, api_client, address):
        assert api_client.get(address)["Location"] == ES

    @pytest.mark.parametrize("address", ADDRESSES)
    @pytest.mark.parametrize(
        ("header", "expected"),
        [("ca", CA), ("ca-ES,ca;q=0.9,en;q=0.8", CA), ("en", EN), ("en-GB,en;q=0.9", EN)],
    )
    def test_it_follows_the_language_of_the_browser(self, api_client, address, header, expected):
        response = api_client.get(address, HTTP_ACCEPT_LANGUAGE=header)

        assert response["Location"] == expected

    @pytest.mark.parametrize("address", ADDRESSES)
    def test_a_language_without_a_form_is_the_spanish_one(self, api_client, address):
        assert api_client.get(address, HTTP_ACCEPT_LANGUAGE="fr-FR,fr;q=0.9")["Location"] == ES

    @pytest.mark.parametrize("address", ADDRESSES)
    def test_the_answer_depends_on_the_header_and_says_so(self, api_client, address):
        """Whatever sits in front of the app must not hand the Catalan form to a
        Spanish browser."""
        assert "Accept-Language" in api_client.get(address)["Vary"]

    @pytest.mark.parametrize("address", ADDRESSES)
    def test_nobody_needs_to_be_signed_in(self, api_client, authenticated_client, address):
        assert api_client.get(address).status_code == status.HTTP_302_FOUND
        assert authenticated_client.get(address).status_code == status.HTTP_302_FOUND

    @pytest.mark.parametrize("address", ADDRESSES)
    def test_it_is_this_apps_route_and_not_the_spa_catch_all(self, address):
        """Both spellings are declared on purpose: the slash-less one resolves to the
        catch-all otherwise, and Django's APPEND_SLASH never gets to fix it."""
        assert resolve(address).app_name == "hosted"

    @pytest.mark.parametrize("address", ADDRESSES)
    def test_the_page_that_was_here_is_not_served_any_more(self, api_client, address):
        response = api_client.get(address, follow=False)

        assert b"Ask to run a group here" not in response.content


@pytest.mark.django_db
class TestTheContactPage:
    """`/contact` is a page of core's; here its address goes to the "Contact us" form.

    Without a route the address falls into the SPA's catch-all and shows core's own contact
    page, a second contact channel next to the Tally form the footer points at.
    """

    ADDRESSES = ["/contact/", "/contact"]

    @pytest.mark.parametrize("address", ADDRESSES)
    def test_it_redirects_with_a_302_and_not_a_permanent_move(self, api_client, address):
        response = api_client.get(address)

        assert response.status_code == status.HTTP_302_FOUND
        assert response.status_code != status.HTTP_301_MOVED_PERMANENTLY

    @pytest.mark.parametrize("address", ADDRESSES)
    def test_with_no_language_header_it_is_the_spanish_form(self, api_client, address):
        assert api_client.get(address)["Location"] == CONTACT_ES

    @pytest.mark.parametrize("address", ADDRESSES)
    @pytest.mark.parametrize(
        ("header", "expected"),
        [
            ("ca-ES", CONTACT_CA),
            ("ca-ES,ca;q=0.9,en;q=0.8", CONTACT_CA),
            ("en", CONTACT_EN),
            ("en-GB,en;q=0.9", CONTACT_EN),
        ],
    )
    def test_it_follows_the_language_of_the_browser(self, api_client, address, header, expected):
        response = api_client.get(address, HTTP_ACCEPT_LANGUAGE=header)

        assert response["Location"] == expected

    @pytest.mark.parametrize("address", ADDRESSES)
    def test_a_language_without_a_form_is_the_spanish_one(self, api_client, address):
        response = api_client.get(address, HTTP_ACCEPT_LANGUAGE="fr")

        assert response["Location"] == CONTACT_ES

    @pytest.mark.parametrize("address", ADDRESSES)
    def test_the_answer_depends_on_the_header_and_says_so(self, api_client, address):
        """Whatever sits in front of the app must not hand the Catalan form to a
        Spanish browser."""
        assert "Accept-Language" in api_client.get(address)["Vary"]

    @pytest.mark.parametrize("address", ADDRESSES)
    def test_it_is_the_contact_form_and_not_the_request_access_one(self, api_client, address):
        assert api_client.get(address)["Location"] != ES

    @pytest.mark.parametrize("address", ADDRESSES)
    def test_nobody_needs_to_be_signed_in(self, api_client, authenticated_client, address):
        assert api_client.get(address).status_code == status.HTTP_302_FOUND
        assert authenticated_client.get(address).status_code == status.HTTP_302_FOUND

    @pytest.mark.parametrize("address", ADDRESSES)
    def test_it_is_this_apps_route_and_not_the_spa_catch_all(self, address):
        """Both spellings are declared on purpose: the slash-less one resolves to the
        catch-all otherwise, and Django's APPEND_SLASH never gets to fix it."""
        assert resolve(address).app_name == "hosted"

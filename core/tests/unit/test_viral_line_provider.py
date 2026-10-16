"""`VIRAL_LINE_PROVIDER` — a deployment chooses each recipient's growth line.

Without the setting the line is a random one from core's catalogue. With it, the
dotted path names `provider(user, lang) -> {"text", "cta", "path"} | None`, called
once per email for the one recipient. Whatever it does wrong costs the email its
line and never the email itself.
"""

import logging
from unittest.mock import patch

import pytest
from django.core import mail
from django.core.checks import Error
from django.test import override_settings

from core.checks import check_viral_line_provider
from core.services import email_service
from core.services.email_texts import viral_lines
from core.tests import sample_viral_provider as sample

PROVIDER = "core.tests.sample_viral_provider.provider"
BASE = "http://localhost:5173"


@pytest.fixture(autouse=True)
def _fresh_provider():
    sample.calls.clear()
    yield
    sample.calls.clear()


def send(address="lili@your-domain.test", lang=None):
    mail.outbox.clear()
    email_service.send_magic_link_email(address, f"{BASE}/verify/tok", lang=lang)
    message = mail.outbox[0]
    return message.body, message.alternatives[0][0]


def with_provider(path=PROVIDER):
    return override_settings(VIRAL_LINE_PROVIDER=path, FRONTEND_URL=BASE)


@pytest.mark.django_db
class TestWithoutTheSetting:
    def test_the_line_comes_from_core_catalogue_as_before(self):
        with override_settings(VIRAL_LINE_PROVIDER=""):
            plain, html = send(lang="en")
        assert any(line["text"] in plain for line in viral_lines("en"))
        assert "background-color:#fff1a8" in html
        assert sample.calls == []


@pytest.mark.django_db
class TestWithTheSetting:
    def test_the_email_carries_the_providers_text_cta_and_link_in_both_formats(self):
        with with_provider():
            plain, html = send(lang="en")
        assert "Open <b>yours</b> & share" in plain
        assert f"Start <here>: {email_service._frontend_base_url()}/stall/new" in plain
        assert 'href="' + email_service._frontend_base_url() + '/stall/new"' in html
        assert "Open &lt;b&gt;yours&lt;/b&gt; &amp; share" in html
        assert "Start &lt;here&gt;" in html
        assert "<b>yours</b>" not in html
        assert "background-color:#fff1a8" in html

    def test_the_catalogue_is_not_used_when_a_provider_answers(self):
        with with_provider():
            plain, _ = send(lang="en")
        assert not any(line["text"] in plain for line in viral_lines("en"))

    def test_the_provider_gets_the_recipient_and_their_language(self, user):
        user.email = "lili@your-domain.test"
        user.save()
        with with_provider():
            send(user.email, lang="ca")
        [(got_user, got_lang)] = sample.calls
        assert got_user.code == user.code
        assert got_lang == "ca"

    def test_an_address_with_no_account_is_passed_as_none(self):
        with with_provider():
            send("nobody@your-domain.test", lang="es")
        assert sample.calls == [(None, "es")]

    def test_none_means_no_line_and_the_rest_of_the_footer_stays(self):
        with with_provider(), patch.object(sample, "answer", lambda user, lang: None):
            plain, html = send(lang="en")
        assert "background-color:#fff1a8" not in html
        # A magic link is mandatory mail, so the legal link is the footer's last line.
        assert plain.rstrip().endswith(f"{email_service._frontend_base_url()}/legal")
        assert html.rstrip().endswith("</a></p></div></div></html>")

    def test_a_provider_that_raises_still_sends_the_email_without_a_line(self, caplog):
        def boom(user, lang):
            raise RuntimeError("lili@your-domain.test is not in our table")

        with with_provider(), patch.object(sample, "answer", boom):
            with caplog.at_level(logging.WARNING):
                plain, html = send("lili@your-domain.test", lang="en")
        assert len(mail.outbox) == 1
        assert "background-color:#fff1a8" not in html
        assert "/legal" in plain
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert any(PROVIDER in r.getMessage() for r in warnings)
        assert not any("lili@your-domain.test" in r.getMessage() for r in warnings)
        assert not any(r.exc_info for r in warnings)

    @pytest.mark.parametrize(
        "path",
        ["https://evil.example", "//evil.example", "evil.example/new", "", "/\\evil.example"],
    )
    def test_a_path_that_leaves_the_site_means_no_line(self, path):
        line = {"text": "Go", "cta": "Now", "path": path}
        with with_provider(), patch.object(sample, "answer", lambda user, lang: line):
            plain, html = send(lang="en")
        assert "evil.example" not in plain and "evil.example" not in html
        assert "background-color:#fff1a8" not in html

    @pytest.mark.parametrize(
        "answer",
        [{"cta": "Now", "path": "/new"}, {"text": "Go", "path": "/new"}, "a string", 7],
        ids=["no-text", "no-cta", "not-a-dict", "a-number"],
    )
    def test_an_answer_that_is_not_a_line_means_no_line(self, answer):
        with with_provider(), patch.object(sample, "answer", lambda user, lang: answer):
            _, html = send(lang="en")
        assert "background-color:#fff1a8" not in html

    def test_someone_who_runs_a_collection_gets_no_line_and_is_not_asked(self, user, collection):
        assert collection.owner_id == user.code
        with with_provider():
            _, html = send(user.email, lang="en")
        assert sample.calls == []
        assert "background-color:#fff1a8" not in html

    def test_the_provider_is_resolved_once_per_path(self):
        email_service._viral_provider.cache_clear()
        with with_provider():
            send(lang="en")
            send(lang="en")
        assert email_service._viral_provider.cache_info().currsize == 1
        assert email_service._viral_provider.cache_info().hits >= 1


class TestTheCheck:
    def test_an_empty_setting_has_no_check(self):
        with override_settings(VIRAL_LINE_PROVIDER=""):
            assert check_viral_line_provider(None) == []

    def test_a_real_function_passes(self):
        with override_settings(VIRAL_LINE_PROVIDER=PROVIDER):
            assert check_viral_line_provider(None) == []

    def test_a_path_that_does_not_import_is_an_error(self):
        with override_settings(VIRAL_LINE_PROVIDER="deployment.viral.Typo"):
            errors = check_viral_line_provider(None)
        assert [e.id for e in errors] == ["core.E006"]
        assert isinstance(errors[0], Error)
        assert "VIRAL_LINE_PROVIDER" in errors[0].msg
        assert "deployment.viral.Typo" in errors[0].msg

    def test_something_importable_that_is_not_callable_is_an_error(self):
        with override_settings(VIRAL_LINE_PROVIDER="core.tests.sample_viral_provider.not_callable"):
            assert [e.id for e in check_viral_line_provider(None)] == ["core.E006"]

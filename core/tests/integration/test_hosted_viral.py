"""This deployment's growth lines, and where each recipient is sent from them.

**Tests code that is not in the standalone.** What it protects: a line in an email
never sends somebody to a form that would refuse them. Whoever this deployment lets
open what the line talks about goes to the form; whoever has to ask first goes to
the page that explains how to ask for exactly what is missing, and the most specific
missing thing wins, so the interest each "ask" measures is the interest it names.
"""

import pytest
from django.core import mail
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from core.models import User
from core.services import email_service
from hosted import viral
from hosted.models import CreatorValidation

PICK = "hosted.viral.pick_line"

# Where an account that has not been validated is sent from each line (1-15, in the
# order the lines are written): a stall is open to everyone, community stalls included;
# a library, whether it lends or rents, and a shed have a page to ask on.
UNVALIDATED = {
    1: "/stall/new",
    2: "/stall/new",
    3: "/stall/new",
    4: "/stall/new",
    5: "/stall/new",
    6: "/stall/new",
    7: "/access/library",
    8: "/access/library",
    9: "/access/library",
    10: "/access/shed",
    11: "/access/shed",
    12: "/access/shed",
    13: "/stall/new",
    14: "/access/library",
    15: "/new",
}
VALIDATED = {
    1: "/stall/new",
    2: "/stall/new",
    3: "/stall/new",
    4: "/stall/new",
    5: "/stall/new",
    6: "/access/community",
    7: "/access/library",
    8: "/access/rent",
    9: "/access/rent",
    10: "/access/shed",
    11: "/access/shed",
    12: "/access/shed",
    13: "/access/community",
    14: "/access/community",
    15: "/new",
}
VALIDATED = {
    1: "/stall/new",
    2: "/stall/new",
    3: "/stall/new",
    4: "/stall/new",
    5: "/stall/new",
    6: "/stall/new",
    7: "/library/new",
    8: "/library/new",
    9: "/library/new",
    10: "/shed/new",
    11: "/shed/new",
    12: "/shed/new",
    13: "/stall/new",
    14: "/library/new",
    15: "/new",
}


def approve(user):
    return CreatorValidation.objects.create(
        user=user,
        who="A neighbour",
        intent="A tool library",
        status=CreatorValidation.Status.APPROVED,
        resolved=timezone.now(),
    )


@pytest.fixture(autouse=True)
def hosted_policy(settings):
    settings.CREATOR_POLICY = "hosted.policy.HostedCreatorPolicy"


@pytest.fixture
def every_line(monkeypatch):
    """Walk the fifteen lines in order, one call each, instead of at random."""

    def walk(user, lang="es"):
        paths = []
        for index in range(len(viral.LINES)):
            monkeypatch.setattr(viral.random, "choice", lambda seq, i=index: seq[i])
            # A fresh object per line: the policy keeps its answer on the user, and
            # these cases are about the answer, not about reusing it.
            paths.append(viral.pick_line(user, lang)["path"])
        return paths

    return walk


class TestTheLines:
    def test_the_three_languages_have_the_same_fifteen_lines_in_the_same_order(self):
        assert len(viral.LINES) == 15
        for line in viral.LINES:
            assert set(line) == {"need", "es", "ca", "en"}
            assert set(line["need"]) == {"kind"}
            for lang in viral.LANGS:
                assert line[lang]["text"].strip()
                assert line[lang]["cta"].strip()

    def test_the_needs_are_the_kind_each_line_talks_about(self):
        kinds = [line["need"]["kind"] for line in viral.LINES]
        assert kinds == (
            ["STALL"] * 6 + ["LIBRARY"] * 3 + ["SHED"] * 3 + ["STALL", "LIBRARY"] + [None]
        )


@pytest.mark.django_db
class TestWhereEachRecipientIsSent:
    def test_an_account_that_has_not_asked_is_sent_to_what_it_can_act_on(self, user, every_line):
        assert dict(enumerate(every_line(user), start=1)) == UNVALIDATED

    def test_a_validated_account_is_sent_to_every_form_and_never_to_the_access_page(
        self, user, every_line
    ):
        approve(user)

        paths = every_line(User.objects.get(pk=user.pk))

        assert dict(enumerate(paths, start=1)) == VALIDATED
        assert not any(path.startswith("/access") for path in paths)

    def test_an_address_with_no_account_is_treated_as_one_that_has_not_asked(self, every_line):
        assert dict(enumerate(every_line(None), start=1)) == UNVALIDATED

    @pytest.mark.parametrize("index", [6, 7, 8, 13])
    def test_lending_and_renting_are_one_page_to_ask_on(self, user, monkeypatch, index):
        """On this deployment one permission covers the whole library, so a line that
        lends, one that rents out and a community library all lead to the same page."""
        monkeypatch.setattr(viral.random, "choice", lambda seq: seq[index])

        assert viral.pick_line(user, "es")["path"] == "/access/library"

    @pytest.mark.parametrize("index", [5, 12])
    def test_a_community_stall_is_just_a_stall(self, user, monkeypatch, index):
        """A stall is open to everyone, in either mode: there is nothing to ask for."""
        monkeypatch.setattr(viral.random, "choice", lambda seq: seq[index])

        assert viral.pick_line(user, "es")["path"] == "/stall/new"

    def test_the_policy_is_asked_once_per_line(self, user, monkeypatch):
        monkeypatch.setattr(viral.random, "choice", lambda seq: seq[7])
        user = User.objects.get(pk=user.pk)

        with CaptureQueriesContext(connection) as queries:
            viral.pick_line(user, "es")

        assert len(queries) == 1

    def test_capabilities_are_resolved_once_per_line(self, user, monkeypatch):
        calls = []
        real = viral.capabilities_for
        monkeypatch.setattr(viral, "capabilities_for", lambda u: calls.append(u) or real(u))

        viral.pick_line(user, "es")

        assert len(calls) == 1

    def test_an_address_with_no_account_costs_no_query(self, django_assert_num_queries):
        with django_assert_num_queries(0):
            viral.pick_line(None, "es")


@pytest.mark.django_db
class TestTheLanguage:
    def test_catalan_gets_catalan_text(self, user, monkeypatch):
        monkeypatch.setattr(viral.random, "choice", lambda seq: seq[0])

        line = viral.pick_line(user, "ca")

        assert line["text"].startswith("Renoves l'armari?")
        assert line["cta"] == "Comença aquí"

    def test_english_gets_english_text(self, user, monkeypatch):
        monkeypatch.setattr(viral.random, "choice", lambda seq: seq[0])

        assert viral.pick_line(user, "en")["cta"] == "Start here"

    def test_a_language_this_deployment_does_not_write_gets_spanish(self, user, monkeypatch):
        monkeypatch.setattr(viral.random, "choice", lambda seq: seq[0])

        line = viral.pick_line(user, "pt")

        assert line["cta"] == "Empieza aquí"


@pytest.mark.django_db
class TestInARealEmail:
    def _send(self, address, lang="en"):
        mail.outbox.clear()
        email_service.send_magic_link_email(address, "http://localhost:5173/verify/tok", lang=lang)
        return mail.outbox[0].body, mail.outbox[0].alternatives[0][0]

    def test_the_magic_link_carries_the_line_and_where_this_recipient_acts(self, user, monkeypatch):
        monkeypatch.setattr(viral.random, "choice", lambda seq: seq[7])  # rent out from a library

        with override_settings(VIRAL_LINE_PROVIDER=PICK):
            plain, html = self._send(user.email)

        base = email_service._frontend_base_url()
        assert viral.LINES[7]["en"]["text"] in plain
        assert f"{viral.LINES[7]['en']['cta']}: {base}/access/library" in plain
        assert f'href="{base}/access/library"' in html

    def test_a_validated_recipient_is_sent_to_the_form(self, user, monkeypatch):
        approve(user)
        monkeypatch.setattr(viral.random, "choice", lambda seq: seq[7])

        with override_settings(VIRAL_LINE_PROVIDER=PICK):
            plain, _ = self._send(user.email)

        assert f"{email_service._frontend_base_url()}/library/new" in plain

    def test_the_line_costs_a_send_at_most_one_query(self, user, monkeypatch):
        with CaptureQueriesContext(connection) as without:
            self._send(user.email)
        monkeypatch.setattr(viral.random, "choice", lambda seq: seq[7])
        with override_settings(VIRAL_LINE_PROVIDER=PICK):
            with CaptureQueriesContext(connection) as with_provider:
                self._send(user.email)

        assert len(with_provider) <= len(without) + 1

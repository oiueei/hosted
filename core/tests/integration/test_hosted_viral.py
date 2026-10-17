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

# What each line (1-15, in the order the lines are written) needs, and where an account
# that has not been validated is sent: the stall's form for 1-5, the generic chooser
# for 15, and the page for what is missing for the rest.
UNVALIDATED = {
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
            assert set(line["need"]) == {"kind", "paid", "community"}
            for lang in viral.LANGS:
                assert line[lang]["text"].strip()
                assert line[lang]["cta"].strip()

    def test_the_needs_are_what_the_lines_talk_about(self):
        needs = [
            (line["need"]["kind"], line["need"]["paid"], line["need"]["community"])
            for line in viral.LINES
        ]
        assert needs == [
            ("STALL", False, False),
            ("STALL", False, False),
            ("STALL", False, False),
            ("STALL", False, False),
            ("STALL", False, False),
            ("STALL", False, True),
            ("LIBRARY", False, False),
            ("LIBRARY", True, False),
            ("LIBRARY", True, False),
            ("SHED", False, False),
            ("SHED", False, False),
            ("SHED", False, False),
            ("STALL", False, True),
            ("LIBRARY", False, True),
            (None, False, False),
        ]


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

    def test_renting_is_named_before_the_library_it_belongs_to(self, user, monkeypatch):
        """Someone who lacks the whole library also lacks renting; the page that
        counts "I want to rent" has to be the one they are sent to."""
        monkeypatch.setattr(viral.random, "choice", lambda seq: seq[7])  # rent from a library

        assert viral.pick_line(user, "es")["path"] == "/access/rent"

    def test_a_community_is_named_before_everything_else(self, user, monkeypatch):
        monkeypatch.setattr(viral.random, "choice", lambda seq: seq[13])  # a community library

        assert viral.pick_line(user, "es")["path"] == "/access/community"

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
        monkeypatch.setattr(viral.random, "choice", lambda seq: seq[7])  # rent from a library

        with override_settings(VIRAL_LINE_PROVIDER=PICK):
            plain, html = self._send(user.email)

        base = email_service._frontend_base_url()
        assert viral.LINES[7]["en"]["text"] in plain
        assert f"{viral.LINES[7]['en']['cta']}: {base}/access/rent" in plain
        assert f'href="{base}/access/rent"' in html

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

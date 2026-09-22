"""`send_test_emails`: one sample of every email, to one address, leaving nothing behind.

It exists so every email can be opened in a real client (CA, 2026-09-21: Apple Mail
drew a logo giant that Gmail drew small — no test can see that). What has to hold
is what makes it safe to point at production: it can mail nobody but ``--to``, and
it changes nothing. And because it drives every builder in every language, it is
also the broadest smoke test the emails have.
"""

import ast
import inspect
import re

import pytest
from django.core import mail
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

from core.management.commands.send_test_emails import LANGS, SAMPLES
from core.models import Collection, Thing, User
from core.services import email_service

TO = "tester@example.org"


def _run(*args):
    mail.outbox.clear()
    call_command("send_test_emails", "--to", TO, *args)
    return list(mail.outbox)


def _send_functions():
    """Every public `send_*` builder in `email_service`, read from the source."""
    tree = ast.parse(inspect.getsource(email_service))
    return {
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name.startswith("send_")
    }


def test_every_email_the_service_can_send_has_a_sample():
    """A new `send_*` builder that nobody added here would be an email nobody ever
    opens in a client before it reaches a person. This fails until it has a sample."""
    covered = {s.covers for s in SAMPLES}

    assert _send_functions() - covered == set()
    # And nothing here names a function that no longer exists.
    assert covered - _send_functions() == set()


def test_sample_names_are_unique():
    names = [s.name for s in SAMPLES]

    assert len(names) == len(set(names))


@pytest.mark.django_db
def test_it_sends_one_of_each_and_all_to_the_one_address():
    boss = User.objects.create(email="boss@example.com", name="Boss", is_superuser=True)

    sent = _run()

    assert len(sent) == len(SAMPLES)
    # Whatever a builder works out for itself — the capacity alarm goes to the
    # superusers, the contact form to the operator — reaches only --to.
    assert {tuple(m.to) for m in sent} == {(TO,)}
    assert all(not m.cc and not m.bcc for m in sent)
    assert boss.email not in {addr for m in sent for addr in m.to}


@pytest.mark.django_db
def test_every_subject_is_tagged_and_numbered_so_they_sort_and_tell_apart():
    sent = _run()

    total = len(SAMPLES)
    for number, message in enumerate(sent, start=1):
        assert message.subject.startswith(f"[TEST {number:02d}/{total} es ")
    labels = [m.subject.split("]")[0] for m in sent]
    assert len(set(labels)) == total


@pytest.mark.django_db
def test_it_leaves_nothing_behind():
    before = (User.objects.count(), Collection.objects.count(), Thing.objects.count())

    _run()

    assert (User.objects.count(), Collection.objects.count(), Thing.objects.count()) == before
    assert not User.objects.filter(email=TO).exists()
    assert not User.objects.filter(email__endswith=".sample@example.com").exists()


@pytest.mark.django_db
def test_an_address_that_is_a_real_account_is_used_then_put_back():
    """The recipient may well have an account. It is used as it is — its footer
    link, its name — but its language and notification switches are forced for the
    run so the samples arrive as a fresh recipient would get them, and the rollback
    restores the account exactly."""
    account = User.objects.create(
        email=TO, name="Real Person", language="ca", notify_activity=False, notify_news=False
    )

    sent = _run("--lang", "es", "--only", "booking_request")

    assert len(sent) == 2
    # Spanish, not the account's Catalan; and delivered although it opted out.
    assert all("solicitud" in m.subject.lower() for m in sent)
    account.refresh_from_db()
    assert (account.language, account.notify_activity, account.notify_news) == ("ca", False, False)
    assert account.name == "Real Person"


@pytest.mark.django_db
def test_all_languages_sends_every_email_in_each():
    sent = _run("--lang", "all")

    assert len(sent) == len(SAMPLES) * len(LANGS)
    assert {m.subject.split("]")[0].split()[2] for m in sent} == set(LANGS)


@pytest.mark.django_db
def test_no_email_in_any_language_leaks_an_unfilled_placeholder():
    """The command as a smoke test: every builder, in every catalogue, with real
    data. A missing key raises; a wrong `.format` field leaves `{owner}` in the
    text. Neither may reach a person."""
    placeholder = re.compile(r"\{[a-z_]+\}")

    for message in _run("--lang", "all"):
        html = message.alternatives[0][0] if message.alternatives else ""
        for part in (message.subject, message.body, html):
            assert not placeholder.search(part), f"{message.subject}: {placeholder.search(part)}"


@pytest.mark.django_db
def test_the_mark_sits_right_after_the_rule_in_every_html_email():
    """The OIUEEI mark's place is a rule of the layout (CA, 2026-09-22): one
    53x15 mark, right after the <hr> that opens the footer, ahead of whatever
    else applies (viral line, preferences, a digest's mute link) and always
    before the legal link, genuinely last. Checked here across every real
    email in every language — the operator's own mail included, it goes
    through the same layout — rather than on the two or three a unit test
    builds by hand."""
    sent = _run("--lang", "all")

    assert len(sent) == len(SAMPLES) * len(LANGS)
    hr = '<hr style="border:none;border-top:1px solid #ddd;margin-top:24px;">'
    for message in sent:
        html = message.alternatives[0][0]
        assert html.count("cid:oiueei-logo") == 1, message.subject
        assert html.count(hr) == 1, message.subject
        assert html.index(hr) < html.index("cid:oiueei-logo"), message.subject
        assert html.index("cid:oiueei-logo") < html.index("/legal"), message.subject
        # Nothing but the card's own closing tags after the legal link.
        tail = html[html.index("</a></p>", html.index("/legal")) :]
        assert tail.strip() == "</a></p></div></div></html>", message.subject


@pytest.mark.django_db
def test_every_email_uses_exactly_the_three_named_sizes():
    """Three sizes, never a fourth (CA, 2026-09-22, superseding the single
    13px every-email size from a day earlier): EMAIL_BODY_SIZE (14px) for the
    message's own words — paragraphs, buttons, a CTA's fallback link —
    EMAIL_HEADER_SIZE (18px) for the one <h1> parent title, EMAIL_FOOTER_SIZE
    (12px) for the rule-separated block at the foot. Checked on every real
    email in every language, footers and the viral line included (appended
    per recipient by _bottom(), after the template render). The header is at
    most one per email; the footer size is not (mark caption-free, but
    "manage your preferences", the legal link, the viral line and a digest's
    mute line are all footer text)."""
    sizes = re.compile(r"font-size:\s*([0-9.]+px)")
    allowed = {
        email_service.EMAIL_BODY_SIZE,
        email_service.EMAIL_HEADER_SIZE,
        email_service.EMAIL_FOOTER_SIZE,
    }

    for message in _run("--lang", "all"):
        found = sizes.findall(message.alternatives[0][0])
        assert found, message.subject
        assert set(found) <= allowed, (message.subject, sorted(set(found) - allowed))
        assert found.count(email_service.EMAIL_HEADER_SIZE) <= 1, message.subject


def test_the_button_styles_use_the_body_size():
    assert f"font-size:{email_service.EMAIL_BODY_SIZE};" in email_service.BTN_PRIMARY
    assert f"font-size:{email_service.EMAIL_BODY_SIZE};" in email_service.BTN_SECONDARY


@pytest.mark.django_db
def test_every_email_is_the_white_rounded_card_on_the_grey_page():
    """The container (CA, 2026-09-22): a white, rounded box — max-width 600px,
    a 1px #888888 border, 10px radius — sitting on a #F9FAFB page with 40px
    padding. One card per email, every language, the operator's own mail
    included (it goes through the same layout)."""
    for message in _run("--lang", "all"):
        html = message.alternatives[0][0]
        assert "background-color:#f9fafb;padding:40px;" in html
        assert (
            "max-width:600px;margin:0 auto;background-color:#ffffff;"
            "border:1px solid #888888;border-radius:10px;"
        ) in html, message.subject
        assert html.count("border-radius:10px") == 1, message.subject


@pytest.mark.django_db
def test_every_email_names_a_real_parent_or_oiueei():
    """Every email has an <h1> now (CA, 2026-09-22) except the one exempted by
    design — the operator's own capacity alarm, internal ops mail with no i18n
    catalogue at all (see send_collection_capacity_alarm's docstring)."""
    h1 = re.compile(r"<h1[^>]*>(.*?)</h1>")

    for message in _run("--lang", "all"):
        html = message.alternatives[0][0]
        found = h1.findall(html)
        if "capacity_alarm" in message.subject:
            assert found == [], message.subject
            continue
        assert len(found) == 1, message.subject
        assert found[0].strip(), message.subject


@pytest.mark.django_db
def test_every_link_in_the_body_is_bus_blue_and_underlined():
    """The design rule (CA, 2026-09-22): every plain text link — the CTA
    fallback link, "manage your preferences", the legal link, the viral
    line's CTA — is bus blue and underlined, never the client's own default
    blue. Buttons are excluded on purpose: a button is not a text link (its
    own style carries no text-decoration at all, which is what keeps it from
    looking like one)."""
    style = 'style="color:#0000bf;text-decoration:underline;"'
    for message in _run("--lang", "all"):
        html = message.alternatives[0][0]
        plain_links = re.findall(r"<a href=[^>]*>", html)
        # At least the legal link is always a plain text link.
        assert any(style in a for a in plain_links), message.subject
        for a in plain_links:
            if a.startswith(f'<a href="{email_service._frontend_base_url()}/legal"'):
                assert style in a, message.subject


@pytest.mark.django_db
def test_only_narrows_the_samples():
    sent = _run("--only", "invite")

    assert 0 < len(sent) < len(SAMPLES)
    assert all("invite" in m.subject for m in sent)


@pytest.mark.django_db
def test_a_builder_that_breaks_does_not_stop_the_rest(monkeypatch, capsys):
    """One broken email must not hide the state of the other thirty-four."""

    def boom(*args, **kwargs):
        raise RuntimeError("template exploded")

    monkeypatch.setattr(email_service, "send_digest_email", boom)

    sent = _run()

    assert len(sent) == len(SAMPLES) - 1
    assert "FAILED" in capsys.readouterr().err


def test_the_address_is_required():
    with pytest.raises(CommandError, match="--to is required"):
        call_command("send_test_emails")
    with pytest.raises(CommandError, match="--to is required"):
        call_command("send_test_emails", "--to", "not-an-address")


@pytest.mark.django_db
def test_an_unknown_filter_is_an_error_not_a_silent_nothing():
    with pytest.raises(CommandError, match="No sample matches"):
        call_command("send_test_emails", "--to", TO, "--only", "zzz-nothing")


@pytest.mark.django_db
def test_a_real_backend_needs_yes_so_a_typo_cannot_send_thirty_five_emails():
    """Nothing is sent, and nothing is built, until the operator confirms."""
    with override_settings(EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend"):
        with pytest.raises(CommandError, match="--yes"):
            call_command("send_test_emails", "--to", TO)


def test_list_prints_the_samples_and_sends_nothing(capsys):
    mail.outbox.clear()

    call_command("send_test_emails", "--list")

    out = capsys.readouterr().out
    assert f"{len(SAMPLES)} samples" in out
    assert all(s.name in out for s in SAMPLES)
    assert mail.outbox == []

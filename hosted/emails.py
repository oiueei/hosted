"""The emails this deployment sends that OIUEEI does not.

It is built from `core.services.email_service`'s own block helpers rather than
re-rendering HTML here, so an ops mail keeps looking like every other mail the
platform sends and inherits the escaping. Those helpers are private to that
module (`_heading`, `_field`, …) and are imported anyway, deliberately: this app
is a consumer of the product living in the same process, and the alternative —
copying the layout — is the version that rots.
"""

import os

from django.conf import settings
from django.urls import reverse

from core.services.email_service import (
    CATEGORY_MANDATORY,
    _field,
    _frontend_base_url,
    _heading,
    _links,
    _para,
    _render_email,
    _send,
    resolve_email_language,
)

from .email_texts import t


def send_stats_summary_email(recipient, subject, sections):
    """Email the first-party stats summary to whoever runs this deployment.

    ``sections`` is the structure the ``stats_summary`` command builds: a list of
    ``{"title": str, "rows": [(label, value), ...], "note"?: str}``. Sent as
    CATEGORY_MANDATORY — an internal ops report, not a user notification, so it
    ignores ``notify_*`` prefs and carries no footer, and `include_viral=False`
    keeps the growth line off it: the operator does not need selling to.
    """
    blocks = []
    plain_lines = []
    for section in sections:
        blocks.append(_heading(section["title"]))
        plain_lines.append(section["title"])
        for label, value in section["rows"]:
            blocks.append(_field(label, str(value)))
            plain_lines.append(f"  {label}: {value}")
        if section.get("note"):
            blocks.append(_para(section["note"]))
            plain_lines.append(f"  ({section['note']})")
        plain_lines.append("")

    _send(
        recipient,
        subject,
        "\n".join(plain_lines),
        _render_email(blocks),
        CATEGORY_MANDATORY,
        include_viral=False,
    )


def send_creator_validation_request_email(validation):
    """Tell the operator somebody has asked to run a group here.

    Until this existed the request landed in a table and a log line, and the only
    way to learn of it was to go and look. Nobody goes and looks at a table for
    something that arrives a few times a month, so the requests simply waited —
    while the page told each person they would hear back.

    Goes to ``CONTACT_EMAIL``, the address this deployment already answers on
    (the contact form and the capacity alarms both use it), falling back to
    ``DEFAULT_FROM_EMAIL`` the same way. ``Reply-To`` is the person who asked, so
    a "tell me more" is one click and does not have to go through the admin.

    Written in English here rather than through a catalogue: it is an ops mail
    for whoever runs the service, like the stats summary above, and not copy for
    a user. Mandatory category and ``include_viral=False`` for the same reason —
    the operator does not need selling to, and cannot opt out of their own inbox.
    """
    recipient = os.environ.get("CONTACT_EMAIL", "") or settings.DEFAULT_FROM_EMAIL
    user = validation.user
    # reverse(), not the literal prefix: `/oiueei-admin/` is upstream's choice in
    # config/urls.py and this app has no business hardcoding a second copy of it.
    admin_path = reverse("admin:hosted_creatorvalidation_change", args=[validation.pk])
    admin_url = f"{_frontend_base_url()}{admin_path}"

    subject = f"Access request from {user.email}"
    plain = (
        f"{user.email} has asked to run a group here.\n\n"
        f"Who they are:\n{validation.who}\n\n"
        f"What they mean to run:\n{validation.intent}\n\n"
        f"Answer it: {admin_url}\n"
    )
    html = _render_email(
        [
            _heading("Somebody has asked to run a group here"),
            _field("Account", user.email),
            _field("Who they are", validation.who),
            _field("What they mean to run", validation.intent),
            _links((admin_url, "Answer it in the admin")),
        ]
    )
    _send(
        recipient,
        subject,
        plain,
        html,
        CATEGORY_MANDATORY,
        reply_to=[user.email],
        include_viral=False,
    )


def send_creator_validation_decision_email(validation):
    """Tell the person who asked what the answer was — yes **or** no.

    Both, and that is the decision this implements rather than a detail of it.
    The page has always promised "you'll hear back by email"; answering only the
    approvals would leave everyone else waiting for a message that was never
    coming, which is worse than never having promised.

    **The note never travels.** ``CreatorValidation.note`` is the operator's own
    memory, and a written reason invites an argument about rules that are not the
    product's — what the person gets is the decision, and an open door to ask
    again. So the "no" says what is still theirs and where to come back, and
    stops.

    ``CATEGORY_MANDATORY``: this is the answer to something they asked for by
    name, and a notification preference set months earlier must not swallow it.
    ``include_viral=False`` follows the account-deletion mail — growth copy under
    a refusal would be grotesque, and the "yes" already carries the one link that
    is worth following.
    """
    user = validation.user
    lang = resolve_email_language(user=user)
    approved = validation.is_approved
    key = "approved" if approved else "rejected"
    url = f"{_frontend_base_url()}{'/collections/new' if approved else '/request-access/'}"

    _send(
        user.email,
        t(f"{key}_subject", lang),
        t(f"{key}_plain", lang).format(url=url),
        _render_email(
            [
                _para(t(f"{key}_intro", lang)),
                _para(t(f"{key}_body", lang)),
                _links((url, t(f"{key}_cta", lang))),
            ],
            lang=lang,
        ),
        CATEGORY_MANDATORY,
        user=user,
        include_viral=False,
        lang=lang,
    )

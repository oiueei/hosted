"""
Centralized email service for OIUEEI.

All email composition and sending is handled here to avoid
duplicating email logic across views.

Each email belongs to one of three categories (see `_should_send`):
- CATEGORY_MANDATORY: magic links, invitations, revocations — always sent.
- CATEGORY_ACTIVITY: user↔user events (bookings, FAQs, reminders, broadcast)
  — opt-out via User.notify_activity.
- CATEGORY_NEWS: digests — opt-out via User.notify_news.

Cat. 2 and Cat. 3 emails include a footer with a tokenised link to /me/notifications
that lets recipients change preferences without logging in.

HTML bodies are rendered from the autoescaping ``email/layout.html`` template via
small block builders (``_para``/``_strong``/``_field``/``_list``/``_links``/
``_heading``), so user-supplied values are escaped by the template engine — no
manual ``escape()`` in the body composition. Plain-text bodies (no XSS surface)
stay as plain strings.
"""

import functools
import logging
import random
import smtplib
from email.mime.image import MIMEImage

from django.conf import settings
from django.core.mail import BadHeaderError, EmailMultiAlternatives
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.template.loader import render_to_string
from django.utils.html import escape

from core.services.email_texts import T, viral_lines
from core.utils import redact_email, resolve_localized

logger = logging.getLogger(__name__)

CATEGORY_MANDATORY = "mandatory"
CATEGORY_ACTIVITY = "activity"
CATEGORY_NEWS = "news"


_PREFS_TOKEN_SALT = "notifications-prefs"
# ~1 year, and deliberately long — this is the shortest TTL of any bearer
# credential we hand out, judged the other way round from the rest.
#
# It looks like a token that should expire fast: it sits in a URL path, in the
# footer of every Cat. 2 / Cat. 3 email, and it authenticates without a login.
# But weigh the two sides. Stolen, it can flip exactly two booleans — turn news
# on, or turn activity off so someone misses a hold request. A nuisance, not a
# breach; there is nothing to read and nothing to spend. Expired, it breaks the
# link somebody clicks *to stop receiving email from us* — this is the
# unsubscribe link, whatever the page calls it. A dead one turns withdrawing
# consent into "log in, find the profile editor, scroll to preferences", which
# is friction on a right, in a product that ships an RGPD notice.
#
# So the long TTL is the user-protective choice here, not the lax one. Rotating
# SECRET_KEY still invalidates every outstanding token at once, which is the
# revocation path that matters. Reviewed and kept, 2026-08 security round.
_PREFS_TOKEN_MAX_AGE = 60 * 60 * 24 * 365  # ~1 year — see above before shortening


def make_notifications_token(user):
    """Return a signed, expiring token for the email-footer preferences link.

    A ``TimestampSigner`` signature over the user's code (salt
    ``notifications-prefs``) rather than a stored column: it carries a ~1-year
    TTL (deliberately — see ``_PREFS_TOKEN_MAX_AGE``) and needs no DB lookup or
    per-user secret to mint. Its blast radius is limited to toggling the two
    notification booleans (see NotificationsByTokenView).
    """
    return TimestampSigner(salt=_PREFS_TOKEN_SALT).sign(user.code)


def verify_notifications_token(token):
    """Return the user_code for a valid, unexpired token, else None."""
    from core.models import User

    try:
        user_code = TimestampSigner(salt=_PREFS_TOKEN_SALT).unsign(
            token, max_age=_PREFS_TOKEN_MAX_AGE
        )
    except (BadSignature, SignatureExpired):
        return None
    return user_code if User.objects.filter(code=user_code).exists() else None


_DIGEST_MUTE_SALT = "digest-mute"


def make_digest_mute_token(user, collection):
    """Signed token for the digest footer's one-click 'stop these' link.

    Carries ``{user_code}:{collection_code}`` under its own salt, so it cannot be
    swapped for a preferences token and vice versa. Its blast radius is one row
    in one M2M: at worst someone silences a digest for a member who can turn it
    straight back on from the collection page.

    Same long TTL as the preferences token, for the same reason (see
    ``_PREFS_TOKEN_MAX_AGE``): this is an unsubscribe link, and an expired one
    turns "stop emailing me" into a support request.
    """
    return TimestampSigner(salt=_DIGEST_MUTE_SALT).sign(f"{user.code}:{collection.code}")


def verify_digest_mute_token(token):
    """Return ``(user_code, collection_code)`` for a valid token, else ``None``."""
    try:
        payload = TimestampSigner(salt=_DIGEST_MUTE_SALT).unsign(
            token, max_age=_PREFS_TOKEN_MAX_AGE
        )
    except (BadSignature, SignatureExpired):
        return None
    user_code, _, collection_code = payload.partition(":")
    if not user_code or not collection_code:
        return None
    return user_code, collection_code


# Sentinel for "no prefetched value" — distinct from a looked-up None (the
# recipient has no User row). Lets the multi-recipient senders pass a resolved
# user (or a known-absent None) so _send doesn't re-query _lookup_user per
# recipient.
_UNSET = object()


def _lookup_user(email):
    from django.db.models import Exists, OuterRef

    from core.models import Collection, User

    return (
        User.objects.annotate(
            _owns_collection=Exists(Collection.objects.filter(owner=OuterRef("pk")))
        )
        .filter(email=email)
        .only("code", "language", "notify_activity", "notify_news")
        .first()
    )


def _lookup_users(emails):
    """Bulk-resolve users for a recipient list — one query, not N.

    Returns ``{email: user}`` for the emails that match a User; addresses with no
    User (not-yet-registered invitees) are simply absent, so callers pass
    ``users.get(email)`` (None) and ``_send`` treats them as opted-in non-users
    without firing another lookup.
    """
    from django.db.models import Exists, OuterRef

    from core.models import Collection, User

    return {
        u.email: u
        for u in User.objects.annotate(
            _owns_collection=Exists(Collection.objects.filter(owner=OuterRef("pk")))
        )
        .filter(email__in=list(emails))
        .only("code", "email", "language", "notify_activity", "notify_news")
    }


def resolve_email_language(user=None, collection=None):
    """Which language an email to this recipient speaks.

    Weakest to strongest: the **deployment default** (``EMAIL_LANGUAGE``), the
    **collection's** language (the owner's choice for their group), the
    **recipient's own** preference. Blank means "inherit", so a level only speaks
    when it was actually set. Thing-scoped 1:1 emails (bookings, FAQs, reminders)
    pass no collection — there is no group to speak for — so they are
    the recipient's preference or the deployment default.
    """
    return (
        (getattr(user, "language", "") or "")
        or (getattr(collection, "language", "") or "")
        or getattr(settings, "EMAIL_LANGUAGE", "en")
    )


def _texts(lang):
    """``T`` bound to one language.

    Senders shadow the module-level ``T`` with it (``T = _texts(lang)``), so every
    ``T("key")`` in the body below speaks the recipient's language without
    threading the argument through each call.
    """
    return functools.partial(T, lang=lang)


def _local(lang):
    """``resolve_localized`` bound to one language.

    Senders bind it as ``L`` next to ``T`` and pass **every owner-written value**
    through it — a headline may carry one text per language (inline JSON, see
    ``core.utils.parse_localized``), and the recipient must read theirs rather than
    the raw map. Plain headlines, which is nearly all of them, come back untouched.
    """
    return functools.partial(resolve_localized, lang=lang)


def _recipient(email, collection=None):
    """Resolve the recipient User once, plus the language their email speaks.

    The User is then handed to ``_send`` so the preference check, the footer link
    and the viral-line gate don't look it up all over again.
    """
    user = _lookup_user(email)
    return user, resolve_email_language(user=user, collection=collection)


def _muted_codes(collection):
    """User codes that have silenced this collection's digest (empty set if none).

    Only consulted for CATEGORY_NEWS: the mute is per group and about *this
    group's news*, so it must not reach the activity emails — a member who
    silences a chatty collection still gets told when their own hold is
    confirmed there.
    """
    if collection is None:
        return set()
    # Memoised on the instance: `_send_per_language` calls `_send` (and so
    # `_should_send`) once per recipient, and without this the belt-and-braces
    # re-check would cost one query per member of the group — the N+1 that a
    # digest to a 200-member collection would notice.
    cached = getattr(collection, "_digest_muted_codes", None)
    if cached is None:
        cached = set(collection.digest_muted.values_list("code", flat=True))
        collection._digest_muted_codes = cached
    return cached


def _should_send(email, category, user=_UNSET, collection=None):
    """True unless the recipient has opted out of this category.

    ``user`` may be prefetched by a multi-recipient sender (a User, or None once
    it is known the recipient has no User row); leave it as ``_UNSET`` for the
    single-recipient path, which looks the user up here.

    ``collection`` narrows CATEGORY_NEWS by the per-collection mute. The check
    lives here, beside the global one, so it holds for any future single-
    recipient news sender rather than only for the bulk path digests use today.
    """
    if category == CATEGORY_MANDATORY:
        return True
    if user is _UNSET:
        user = _lookup_user(email)
    if not user:
        return True
    if category == CATEGORY_ACTIVITY:
        return user.notify_activity
    if category == CATEGORY_NEWS:
        return user.notify_news and user.code not in _muted_codes(collection)
    return True


def _filter_recipients(emails, category, collection=None):
    """Filter a bulk recipient list, removing users who have opted out.

    Two independent opt-outs for news: the global ``notify_news`` switch and,
    when the mail belongs to a collection, that collection's own mute list.
    """
    if category == CATEGORY_MANDATORY:
        return list(emails)
    from core.models import User

    field = "notify_activity" if category == CATEGORY_ACTIVITY else "notify_news"
    opted_out = set(
        User.objects.filter(email__in=list(emails), **{field: False}).values_list(
            "email", flat=True
        )
    )
    if category == CATEGORY_NEWS and collection is not None:
        muted = set(
            collection.digest_muted.filter(email__in=list(emails)).values_list("email", flat=True)
        )
        opted_out |= muted
    return [e for e in emails if e not in opted_out]


def _send_per_language(
    emails, category, compose, collection=None, reply_to=None, extra_footer=None
):
    """Send one bulk email (digest, broadcast) to a list of
    recipients, **each in their own language**.

    A group can be bilingual, so the body can't be composed once up front:
    ``compose(lang)`` builds ``(subject, plain, html)`` and is called once per
    distinct language present among the recipients (not once per recipient — a
    50-member group in one language still composes once). Opt-outs are dropped
    first, and the users are bulk-resolved in a single query so ``_send`` doesn't
    re-look-up anyone.
    """
    recipients = _filter_recipients(emails, category, collection=collection)
    users = _lookup_users(recipients)
    composed = {}
    for email in recipients:
        user = users.get(email)
        lang = resolve_email_language(user=user, collection=collection)
        if lang not in composed:
            composed[lang] = compose(lang)
        subject, plain, html = composed[lang]
        # Composed once per language, but this line is per recipient: it carries
        # a token signed for *this* user, so it cannot join the cached body.
        if extra_footer:
            extra = extra_footer(user, lang)
            if extra:
                label, link = extra
                plain = f"{plain}\n\n{label}: {link}"
                html = (
                    f'{html}<p style="color:#666;font-size:12px;">'
                    f'<a href="{escape(link)}">{escape(label)}</a></p>'
                )
        _send(
            email,
            subject,
            plain,
            html,
            category,
            reply_to=reply_to,
            user=user,
            lang=lang,
            collection=collection,
        )


def _frontend_base_url():
    return settings.MAGIC_LINK_BASE_URL.rsplit("/", 1)[0]


def _notifications_link(email, user=_UNSET):
    if user is _UNSET:
        user = _lookup_user(email)
    base = _frontend_base_url()
    if user:
        return f"{base}/me/notifications/{make_notifications_token(user)}"
    return f"{base}/me/notifications"


def _with_footer(plain, html, email, category, user=_UNSET, lang=None):
    """Append the 'manage your emails' footer for Cat. 2 / Cat. 3 emails."""
    if category == CATEGORY_MANDATORY:
        return plain, html
    link = _notifications_link(email, user=user)
    manage = T("footer_manage", lang)
    footer_plain = f"\n\n---\n{manage}: {link}"
    footer_html = (
        '<hr style="border:none;border-top:1px solid #ddd;margin-top:24px;">'
        '<p style="color:#666;font-size:12px;">'
        f'{escape(manage)}: <a href="{escape(link)}">{escape(link)}</a>'
        "</p>"
    )
    return plain + footer_plain, html + footer_html


def _with_viral_line(plain, html, user=_UNSET, lang=None):
    """Prepend one random growth blurb above the preferences footer.

    Shown to recipients who don't own a collection — the audience for "create
    your own" — including not-yet-registered invitees (``user`` is None).
    Suppressed for collection owners and when ``VIRAL_LINES`` is empty. The CTA
    is the plain ``/collections/new`` URL, never tracking-wrapped (DESIGN §9).
    """
    lines = viral_lines(lang)
    if not lines:
        return plain, html
    if user is not _UNSET and user and getattr(user, "_owns_collection", False):
        return plain, html
    line = random.choice(lines)
    url = f"{_frontend_base_url()}/collections/new"
    plain += f"\n\n{line['text']}\n{line['cta']}: {url}"
    html += (
        '<p style="margin-top:24px;font-size:13px;">'
        f"{escape(line['text'])} "
        f'<a href="{escape(url)}">{escape(line["cta"])}</a>'
        "</p>"
    )
    return plain, html


@functools.lru_cache(maxsize=1)
def _logo_bytes():
    """Read the inline email logo once; None if the asset is missing.

    Cached across the process lifetime — the file never changes at runtime, so
    every send after the first skips the filesystem hit. A missing/corrupt
    asset degrades to "no logo" everywhere (attachment and ``<img>`` both
    skipped) rather than failing the send.
    """
    try:
        return (settings.BASE_DIR / "frontend/public/oiueei-logo.png").read_bytes()
    except OSError:
        return None


def _logo_attachment():
    """Return the logo as an inline MIMEImage (Content-ID ``oiueei-logo``), or None."""
    data = _logo_bytes()
    if data is None:
        return None
    image = MIMEImage(data, "png")
    image.add_header("Content-ID", "<oiueei-logo>")
    image.add_header("Content-Disposition", "inline", filename="oiueei-logo.png")
    return image


def _send(
    to_email,
    subject,
    plain,
    html,
    category,
    reply_to=None,
    user=_UNSET,
    include_viral=True,
    lang=None,
    collection=None,
):
    """Send a single email through the category + footer + viral pipeline.

    Returns True if the email was dispatched, False if the recipient opted out
    or the send failed. A failed send (SMTP error / timeout / socket error / bad
    header) is logged and swallowed — it never propagates, so it cannot 500 a
    user action whose DB work has already committed, nor abort a multi-recipient
    loop or a nightly cron.

    ``user`` lets a multi-recipient sender (broadcast/digest) pass a
    batch-resolved User (or a known-absent None) so the preference + footer
    lookups don't fire a query per recipient. Single-recipient callers leave it
    as ``_UNSET`` and the lookup happens here, as before.

    ``include_viral`` prepends a growth CTA above the footer (suppressed for
    collection owners — see ``_with_viral_line``). ``send_stats_summary_email``
    is the one sender that passes ``False`` (an operator report, not growth
    copy); everything else, including ``send_magic_link_email`` since S2, uses
    the default — so magic-link sends now do the one recipient lookup they
    used to skip (see that function's docstring for why the extra query is
    still timing-safe).

    ``lang`` is the language the sender composed this email in (see
    ``resolve_email_language``); the footer and the viral line follow it, so the
    whole message speaks one language.
    """
    # Resolve the recipient User once when something downstream needs it: the
    # preference check (non-mandatory) or the viral-line ownership gate. Only
    # the mandatory + include_viral=False send (stats summary) skips it.
    if (category != CATEGORY_MANDATORY or include_viral) and user is _UNSET:
        user = _lookup_user(to_email)
    if not _should_send(to_email, category, user=user, collection=collection):
        return False
    if include_viral:
        plain, html = _with_viral_line(plain, html, user=user, lang=lang)
    plain, html = _with_footer(plain, html, to_email, category, user=user, lang=lang)
    try:
        # Always EmailMultiAlternatives (not the send_mail() shortcut) — the
        # inline logo needs .attach() on the message object, which send_mail()
        # never exposes.
        msg = EmailMultiAlternatives(
            subject=subject, body=plain, from_email=None, to=[to_email], reply_to=reply_to
        )
        msg.attach_alternative(html, "text/html")
        logo = _logo_attachment()
        if logo:
            # The logo is a CID reference, not a loose file: wrap the
            # alternative + image in multipart/related (not the default
            # multipart/mixed). Apple Mail treats a mixed sibling as a normal
            # attachment even when the HTML references its CID, so it rendered
            # the 30px inline logo AND a full-size copy + paperclip at the end
            # (user-reported on iOS Apple Mail).
            msg.mixed_subtype = "related"
            msg.attach(logo)
        msg.send()
    except (smtplib.SMTPException, OSError, BadHeaderError) as exc:
        # OSError covers socket.timeout/connection errors (socket.timeout is an
        # OSError subclass). BadHeaderError (a ValueError) guards against a CR/LF
        # that slipped into the subject — caught here so one tainted row can never
        # abort a multi-recipient loop or a nightly digest cron.
        # Log the exception class only — str(exc) (e.g. SMTPRecipientsRefused)
        # can carry the raw recipient address, which would defeat redaction (M5).
        logger.error(
            "Email send failed (to=%s, subject=%r): %s",
            redact_email(to_email),
            subject,
            type(exc).__name__,
        )
        return False
    return True


# --- HTML body composition (autoescaped via email/layout.html) -----------------


def _para(text):
    """A paragraph of (autoescaped) text."""
    return {"type": "para", "text": text}


def _strong(text):
    """A paragraph holding a single bold value (used for the focal headline)."""
    return {"type": "strong", "text": text}


def _field(label, value):
    """A ``Label: value`` line."""
    return {"type": "field", "label": label, "value": value}


def _heading(text):
    """A section heading (``<h3>``)."""
    return {"type": "heading", "text": text}


def _list(items):
    """A bullet list."""
    return {"type": "list", "items": list(items)}


def _links(*links):
    """A row of links, each ``(url, label)``, joined by ``|``."""
    return {"type": "links", "links": [{"url": url, "label": label} for url, label in links]}


def _render_email(blocks):
    """Render the HTML body from a list of blocks through the autoescaping layout.

    ``has_logo`` mirrors whether ``_send()`` will find the asset to attach —
    the ``cid:`` reference is only rendered when there's a matching attachment
    coming, so a missing file never leaves a broken image in the email.
    """
    return render_to_string(
        "email/layout.html", {"blocks": blocks, "has_logo": _logo_bytes() is not None}
    )


def _booking_detail_blocks(booking, lang=None):
    """Date/quantity detail blocks shared by the three booking emails."""
    if booking.start_date and booking.end_date:
        return [_field(T("dates_label", lang), f"{booking.start_date} - {booking.end_date}")]
    return []


def _thing_url(thing):
    """Build the frontend URL for a thing (collection-scoped when possible)."""
    base = _frontend_base_url()
    collection = thing.collections.first()
    if collection:
        return f"{base}/collections/{collection.code}/things/{thing.code}"
    return f"{base}/things/{thing.code}"


def _action_noun(thing, lang=None):
    """The per-type action noun for the booking emails (e.g. 'purchase', 'compra').

    Mirrors the frontend's per-type vocabulary (``thingCard.action`` / ``types``)
    so a SELL request reads 'solicitud de compra' / 'purchase request', a LEND
    request 'solicitud de préstamo' / 'loan request', etc. Every bookable type
    carries a noun — a missing one would be a KeyError mid-decision, after the
    booking already committed.
    """
    return T(f"action_noun_{thing.type}", lang)


# --- Category 1: Mandatory -----------------------------------------------------


def send_magic_link_email(email, magic_link, collection_headline=None, lang=None):
    """Send magic link authentication email.

    When ``collection_headline`` is given (a pop-in / share-link join), the
    subject names the collection the visitor is joining; without it the generic
    welcome subject is used (``/login`` and the plain onboarding pop-in).

    ``lang`` is resolved by the caller (the auth views know the user and, on a
    join, the collection) so language resolution never looks the recipient up
    on its own (L10, email-enumeration timing oracle). The viral-line gate does
    add one ``User`` lookup inside ``_send()`` now (S2) — safe here because both
    callers only reach this function after already resolving the recipient
    (``RequestLinkView`` only for a confirmed-registered address; ``PopInView``
    after ``get_or_create``), so the extra query carries no new
    registered/unregistered timing signal.
    """
    T = _texts(lang)
    if collection_headline:
        subject = T("magic_subject_collection").format(
            collection=resolve_localized(collection_headline, lang)
        )
    else:
        subject = T("magic_subject")
    plain = T("magic_plain").format(link=magic_link)
    html = _render_email(
        [
            _para(T("magic_intro")),
            _links((magic_link, T("magic_cta"))),
        ]
    )
    _send(email, subject, plain, html, CATEGORY_MANDATORY, lang=lang)


def send_collection_invite_email(
    inviter_name, collection_headline, email, accept_link, reject_link, collection=None
):
    """Send collection invitation email with accept and reject links."""
    user, lang = _recipient(email, collection)
    T, L = _texts(lang), _local(lang)
    headline = L(collection_headline)
    subject = T("invite_subject").format(collection=headline)
    plain = T("invite_plain").format(collection=headline, accept=accept_link, reject=reject_link)
    html = _render_email(
        [
            _para(T("invite_intro").format(inviter=inviter_name)),
            _strong(headline),
            _links((accept_link, T("invite_accept_cta")), (reject_link, T("invite_decline_cta"))),
        ]
    )
    _send(email, subject, plain, html, CATEGORY_MANDATORY, user=user, lang=lang)


def send_collection_welcome_doc_email(collection_headline, doc_url, email, collection=None):
    """Send the collection's welcome & rules PDF to a member who has just joined.

    A **link**, never an attachment: the file lives on Cloudinary, and mailing a
    5 MB PDF to every joiner would be a good way to get the domain filtered.
    Membership lifecycle, so it is mandatory (Cat. 1) like the invitation itself —
    a member who never sees the rules can't follow them. Sent once, on the first
    join (see ``core/views/auth.py::_join_collection``).
    """
    user, lang = _recipient(email, collection)
    T, L = _texts(lang), _local(lang)
    headline = L(collection_headline)
    subject = T("welcome_doc_subject").format(collection=headline)
    plain = T("welcome_doc_plain").format(collection=headline, url=doc_url)
    html = _render_email(
        [
            _para(T("welcome_doc_intro")),
            _links((doc_url, headline)),
            _para(T("welcome_doc_outro")),
        ]
    )
    _send(email, subject, plain, html, CATEGORY_MANDATORY, user=user, lang=lang)


def send_account_delete_email(user, delete_link):
    """Send the right-to-erasure confirmation link (Cat. 1).

    The safety step of account deletion: the in-app button only *requests*
    deletion; nothing is deleted until the recipient opens this link and
    confirms once more on the page it lands on (the link previews on GET and
    commits on POST, like a booking decision — a mail scanner can't erase an
    account). ``include_viral=False``: a growth CTA on an erasure email would
    be grotesque.
    """
    lang = resolve_email_language(user=user)
    T = _texts(lang)
    subject = T("account_delete_subject")
    plain = T("account_delete_plain").format(link=delete_link)
    html = _render_email(
        [
            _para(T("account_delete_intro")),
            _para(T("account_delete_deletes")),
            _para(T("account_delete_keeps")),
            _links((delete_link, T("account_delete_cta"))),
            _para(T("account_delete_outro")),
        ]
    )
    _send(
        user.email,
        subject,
        plain,
        html,
        CATEGORY_MANDATORY,
        user=user,
        include_viral=False,
        lang=lang,
    )


def send_contact_email(name, email, message, kind="support"):
    """Forward a contact-form message to the operator (the support channel).

    Recipient: ``CONTACT_EMAIL`` env var, defaulting to ``DEFAULT_FROM_EMAIL``
    (the operator mails themselves). ``Reply-To`` is the sender, so answering
    is one click. ``kind`` labels the subject — ``support`` (contact page) or
    ``collab`` (collaborate page) — same pipe, different inbox label. Operator
    mail: mandatory category, no viral CTA, deployment language.
    """
    import os

    recipient = os.environ.get("CONTACT_EMAIL", "") or settings.DEFAULT_FROM_EMAIL
    lang = resolve_email_language()
    T = _texts(lang)
    sender = name or email
    subject_key = "collab_subject" if kind == "collab" else "contact_subject"
    subject = T(subject_key).format(sender=sender)
    plain = T("contact_plain").format(name=name or "-", email=email, message=message)
    html = _render_email(
        [
            _para(T("contact_intro")),
            _field(T("contact_name_label"), name or "-"),
            _field(T("contact_email_label"), email),
            _para(message),
        ]
    )
    _send(
        recipient,
        subject,
        plain,
        html,
        CATEGORY_MANDATORY,
        reply_to=[email],
        include_viral=False,
        lang=lang,
    )


def send_collection_revoke_email(owner_name, collection_headline, email, collection=None):
    """Send collection access revoked notification email."""
    user, lang = _recipient(email, collection)
    T, L = _texts(lang), _local(lang)
    headline = L(collection_headline)
    subject = T("revoke_subject")
    plain = T("revoke_plain").format(owner=owner_name, collection=headline)
    html = _render_email(
        [
            _para(T("revoke_intro").format(owner=owner_name)),
            _strong(headline),
            _para(T("revoke_outro")),
        ]
    )
    _send(email, subject, plain, html, CATEGORY_MANDATORY, user=user, lang=lang)


# --- Category 2: Activity ------------------------------------------------------


def send_booking_request_email(requester, thing, booking, owner_email, accept_link, reject_link):
    """Send booking request email to owner with accept/reject links."""
    user, lang = _recipient(owner_email)
    T, L = _texts(lang), _local(lang)
    requester_name = requester.display_name
    action = _action_noun(thing, lang)
    headline = L(thing.headline)

    if booking.start_date and booking.end_date:
        plain = T("booking_request_plain_dated").format(
            requester=requester_name,
            action=action,
            thing=headline,
            start=booking.start_date,
            end=booking.end_date,
            accept=accept_link,
            reject=reject_link,
        )
    else:
        plain = T("booking_request_plain").format(
            requester=requester_name,
            action=action,
            thing=headline,
            accept=accept_link,
            reject=reject_link,
        )

    subject = T("booking_request_subject").format(action=action)
    html = _render_email(
        [
            _para(T("booking_request_intro").format(requester=requester_name, action=action)),
            _strong(headline),
            *_booking_detail_blocks(booking, lang),
            _links((accept_link, T("hold_confirm_cta")), (reject_link, T("hold_cancel_cta"))),
        ]
    )
    _send(owner_email, subject, plain, html, CATEGORY_ACTIVITY, user=user, lang=lang)


def send_booking_decision_email(booking, thing, accepted=True):
    """Send booking accept/reject notification email to requester."""
    user, lang = _recipient(booking.requester_email)
    T, L = _texts(lang), _local(lang)
    decision_word = T("decision_confirmed") if accepted else T("decision_cancelled")
    action = _action_noun(thing, lang)
    headline = L(thing.headline)

    if booking.start_date and booking.end_date:
        plain = T("decision_plain_dated").format(
            action=action,
            thing=headline,
            start=booking.start_date,
            end=booking.end_date,
            decision=decision_word,
        )
    else:
        plain = T("decision_plain").format(action=action, thing=headline, decision=decision_word)

    subject = T("decision_subject")
    html = _render_email(
        [
            _para(T("decision_intro").format(action=action, decision=decision_word)),
            _strong(headline),
            *_booking_detail_blocks(booking, lang),
        ]
    )
    _send(booking.requester_email, subject, plain, html, CATEGORY_ACTIVITY, user=user, lang=lang)


def send_invite_rejected_email(invitee_name, collection_headline, owner_email, collection=None):
    """Send notification to collection owner that an invite was declined."""
    user, lang = _recipient(owner_email, collection)
    T, L = _texts(lang), _local(lang)
    headline = L(collection_headline)
    subject = T("invite_rejected_subject")
    plain = T("invite_rejected_plain").format(invitee=invitee_name, collection=headline)
    html = _render_email(
        [
            _para(T("invite_rejected_intro").format(invitee=invitee_name)),
            _strong(headline),
        ]
    )
    _send(owner_email, subject, plain, html, CATEGORY_ACTIVITY, user=user, lang=lang)


def send_booking_confirmation_email(requester, thing, booking):
    """Send booking confirmation email to the requester."""
    user, lang = _recipient(requester.email)
    T, L = _texts(lang), _local(lang)
    owner_name = thing.owner.display_name
    thing_url = _thing_url(thing)
    collection = thing.collections.first()
    action = _action_noun(thing, lang)
    headline = L(thing.headline)

    if booking.start_date and booking.end_date:
        plain = T("confirmation_plain_dated").format(
            action=action,
            thing=headline,
            start=booking.start_date,
            end=booking.end_date,
            owner=owner_name,
            url=thing_url,
        )
    else:
        plain = T("confirmation_plain").format(
            action=action, thing=headline, owner=owner_name, url=thing_url
        )

    subject = T("confirmation_subject").format(action=action)
    html = _render_email(
        [
            _para(T("confirmation_intro").format(action=action)),
            _strong(headline),
            *([_field(T("part_of_label"), L(collection.headline))] if collection else []),
            *_booking_detail_blocks(booking, lang),
            _para(T("confirmation_outro").format(owner=owner_name)),
            _links((thing_url, headline)),
        ]
    )
    _send(requester.email, subject, plain, html, CATEGORY_ACTIVITY, user=user, lang=lang)


def send_faq_question_email(questioner_name, thing, question, owner_email):
    """Send FAQ question notification email to thing owner."""
    user, lang = _recipient(owner_email)
    T, L = _texts(lang), _local(lang)
    thing_url = _thing_url(thing)
    headline = L(thing.headline)

    subject = T("faq_question_subject")
    plain = T("faq_question_plain").format(
        questioner=questioner_name, thing=headline, question=question, url=thing_url
    )
    html = _render_email(
        [
            _para(T("faq_question_intro").format(questioner=questioner_name)),
            _strong(headline),
            _field(T("question_label"), question),
            _links((thing_url, T("faq_view_reply_cta"))),
        ]
    )
    _send(owner_email, subject, plain, html, CATEGORY_ACTIVITY, user=user, lang=lang)


def send_faq_answer_email(owner_name, thing, question, answer, questioner_email):
    """Send FAQ answer notification email to questioner, linking the thing."""
    user, lang = _recipient(questioner_email)
    T, L = _texts(lang), _local(lang)
    thing_url = _thing_url(thing)
    headline = L(thing.headline)
    subject = T("faq_answer_subject")
    plain = T("faq_answer_plain").format(
        owner=owner_name, answer=answer, thing=headline, url=thing_url
    )
    html = _render_email(
        [
            _para(T("faq_answer_intro").format(owner=owner_name)),
            _strong(headline),
            _field(T("your_question_label"), question),
            _field(T("reply_label"), answer),
            _links((thing_url, headline)),
        ]
    )
    _send(questioner_email, subject, plain, html, CATEGORY_ACTIVITY, user=user, lang=lang)


def send_faq_hide_email(owner_name, thing_headline, question, questioner_email):
    """Send FAQ hidden notification email to questioner."""
    user, lang = _recipient(questioner_email)
    T, L = _texts(lang), _local(lang)
    subject = T("faq_hide_subject")
    plain = T("faq_hide_plain").format(owner=owner_name, question=question)
    html = _render_email(
        [
            _para(T("faq_hide_intro").format(owner=owner_name)),
            _strong(L(thing_headline)),
            _field(T("question_label"), question),
        ]
    )
    _send(questioner_email, subject, plain, html, CATEGORY_ACTIVITY, user=user, lang=lang)


def send_thing_reported_email(thing, owner_email):
    """Notify a thing owner that someone reported their listing.

    The reporter's identity is deliberately never included — the owner learns
    only *that* it was reported and *which* listing, so they can go and check it.
    """
    user, lang = _recipient(owner_email)
    T, L = _texts(lang), _local(lang)
    thing_url = _thing_url(thing)
    headline = L(thing.headline)

    subject = T("reported_subject")
    plain = T("reported_plain").format(thing=headline, url=thing_url)
    html = _render_email(
        [
            _para(T("reported_intro")),
            _strong(headline),
            _para(T("reported_outro")),
            _links((thing_url, T("reported_review_cta"))),
        ]
    )
    _send(owner_email, subject, plain, html, CATEGORY_ACTIVITY, user=user, lang=lang)


def send_broadcast_email(
    owner_name, owner_email, collection_headline, collection_code, message, emails, collection=None
):
    """Send a broadcast email from a collection owner to all invitees.

    The subject is auto-generated as "Hey! {collection}" (the owner only writes
    the message). Carries a reply-to header (the owner) and a link to the
    collection — the object that originated the message — so recipients can open
    it in-app. Composed per recipient language (see ``_compose_per_language``).
    """
    collection_url = f"{_frontend_base_url()}/collections/{collection_code}"

    def compose(lang):
        T, L = _texts(lang), _local(lang)
        headline = L(collection_headline)
        return (
            T("broadcast_subject").format(collection=headline),
            T("broadcast_plain").format(
                owner=owner_name,
                collection=headline,
                message=message,
                url=collection_url,
            ),
            _render_email(
                [
                    _para(T("broadcast_intro").format(owner=owner_name, collection=headline)),
                    _para(message),
                    _links((collection_url, T("broadcast_help_cta"))),
                ]
            ),
        )

    _send_per_language(
        emails, CATEGORY_ACTIVITY, compose, collection=collection, reply_to=[owner_email]
    )


def send_return_reminder_email(requester_name, thing_headline, end_date, owner_email):
    """Remind the owner that a booking ends tomorrow."""
    user, lang = _recipient(owner_email)
    T, L = _texts(lang), _local(lang)
    headline = L(thing_headline)
    subject = T("reminder_subject")
    plain = T("reminder_plain").format(requester=requester_name, thing=headline, end=end_date)
    body = T("reminder_body").format(requester=requester_name, thing=headline, end=end_date)
    html = _render_email([_para(body)])
    _send(owner_email, subject, plain, html, CATEGORY_ACTIVITY, user=user, lang=lang)


# --- Category 3: News / broadcast ---------------------------------------------


def send_digest_email(
    collection_headline, collection_code, thing_headlines, emails, collection=None
):
    """Send a digest email listing new things added to a collection."""
    base_url = _frontend_base_url()
    collection_url = f"{base_url}/collections/{collection_code}"

    def compose(lang):
        T, L = _texts(lang), _local(lang)
        headline = L(collection_headline)
        headlines = [L(h) for h in thing_headlines]
        things_plain = "\n".join(f"  - {h}" for h in headlines)
        return (
            T("digest_subject").format(collection=headline),
            T("digest_plain").format(collection=headline, things=things_plain, url=collection_url),
            _render_email(
                [
                    _para(T("digest_intro").format(collection=headline)),
                    _list(headlines),
                    _links((collection_url, T("view_collection_cta"))),
                ]
            ),
        )

    # The per-collection unsubscribe, appended after the generic preferences
    # footer. It is what lets `notify_news` default to on (DESIGN §6): the way to
    # stop *these* emails is one click in the email itself, and it costs the
    # reader none of the transactional mail they actually want. `_send`'s footer
    # can't build it — it is scoped to a collection, and only this sender has one.
    def per_recipient_footer(user, lang):
        if user is None or collection is None:
            return None
        link = f"{base_url}/digest/mute/{make_digest_mute_token(user, collection)}"
        return T("digest_mute_cta", lang), link

    _send_per_language(
        emails,
        CATEGORY_NEWS,
        compose,
        collection=collection,
        extra_footer=per_recipient_footer,
    )


def send_stats_summary_email(recipient, subject, sections):
    """Email the first-party stats summary to the platform operator.

    ``sections`` is the structure the ``stats_summary`` command builds: a list of
    ``{"title": str, "rows": [(label, value), ...], "note"?: str}``. Sent as
    CATEGORY_MANDATORY — an internal ops report, not a user notification, so it
    ignores ``notify_*`` prefs and carries no footer. Values are escaped by the
    autoescaping layout (they're aggregate numbers, but the pipeline stays uniform).
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


def send_collection_capacity_alarm(collection, counter, count, threshold):
    """Alert the operator that a collection crossed the mass-upload alarm line.

    Ops mail, like ``send_stats_summary_email``: operator-only, so it carries no
    i18n catalogue, no footer and no viral CTA.

    **Recipients are the superusers**, not a config var. The spec says this
    alert reaches the operator alone, and on the deploy branch the operator *is*
    the superuser — so deriving the address from `is_superuser` keeps the two
    definitions from drifting, and a deployment that adds a second admin gets
    them included without touching config. Falls back to ``CONTACT_EMAIL`` /
    ``DEFAULT_FROM_EMAIL`` if no superuser has an email, because an abuse signal
    that silently goes nowhere is worse than no signal.

    **The owner is never copied.** The alarm is a tripwire, not a warning: a
    legitimate bulk import must not be interrupted, and someone probing the
    endpoint must not be told where the line sits. Only the hard ceiling
    (``COLLECTION_THINGS_BLOCK``) is user-visible, and only once it bites.
    """
    import os

    from core.models import User

    recipients = list(
        User.objects.filter(is_superuser=True).exclude(email="").values_list("email", flat=True)
    ) or [os.environ.get("CONTACT_EMAIL", "") or settings.DEFAULT_FROM_EMAIL]
    owner = collection.owner
    headline = resolve_localized(collection.headline)
    noun = "things" if counter == "things" else "members"
    subject = f"[OIUEEI] Collection {collection.code} passed {threshold} {noun}"
    rows = [
        ("Collection", f"{headline} ({collection.code})"),
        ("Counter", noun),
        (noun.capitalize(), str(count)),
        ("Alarm threshold", str(threshold)),
        ("Owner", f"{owner.display_name} <{owner.email}>" if owner else "-"),
        ("Owner code", owner.code if owner else "-"),
        ("Created", collection.created.isoformat()),
    ]
    blocks = [
        _para(
            "A collection has crossed the mass-upload alarm threshold. This is "
            "informational — nothing has been blocked and the owner has not been "
            "notified. Review it if the volume looks wrong for this account."
        )
    ]
    plain_lines = ["Collection passed the mass-upload alarm threshold.", ""]
    for label, value in rows:
        blocks.append(_field(label, value))
        plain_lines.append(f"  {label}: {value}")

    # One send per superuser: _send takes a single address, and a per-recipient
    # send keeps a bad address from costing the others their alert.
    plain = "\n".join(plain_lines)
    html = _render_email(blocks)
    for recipient in recipients:
        _send(recipient, subject, plain, html, CATEGORY_MANDATORY, include_viral=False)

"""Where "Request access" and "Contact us" live on this deployment: forms on Tally.

It used to be a Django page of our own, `/request-access/`, with two free-text questions
and a model row per request. It moved to Tally, as the footer's
"Contact us" and "Ideas and bugs" already were (`frontend/src/deployment/index.js`,
`externalForms`): one form per language, opened in a new tab, and the request lands in
Tally instead of in a table. The answer is still given in the admin
(`CreatorValidation`, which is what grants the permission), so a request that arrives
through Tally is entered there by email (`hosted.admin`).

The SPA reads these same three addresses from its own `externalForms.requestAccess`; the
server needs them in three places the SPA does not render: `capabilities.request_url`
(what `ApprovalNotice` falls back to), the two 403 bodies that name where to ask (a
collection mode and a thing type that are not open yet) and the email that tells
somebody their request was not approved. **They are written twice**, here and in the
JavaScript, and `core/tests/integration/test_hosted_tally.py` reads both files so the
two cannot come apart.

"Contact us" is a Tally form too, one per language, and the footer's link already goes to it
(`externalForms.contact` in the same JavaScript file). The server keeps those three addresses
for the one way to reach it that does not pass through the footer: `/contact`, a page of core's,
typed into the browser or saved in a bookmark (`views.ContactRedirect`). The test above reads
both files for both forms.

The addresses are used exactly as written: nothing about the person is added to them.
"""

from django.utils.translation.trans_real import parse_accept_lang_header

DEFAULT_LANGUAGE = "es"

REQUEST_ACCESS = {
    "es": "https://tally.so/r/zxaY4M",
    "ca": "https://tally.so/r/D4lz9N",
    "en": "https://tally.so/r/aQ8dPX",
}

CONTACT = {
    "es": "https://tally.so/r/PdaOy1",
    "ca": "https://tally.so/r/Gx2lye",
    "en": "https://tally.so/r/Y5LagN",
}


def request_access_url(language=None):
    """The "Request access" form in ``language`` — ``es`` for a blank or unknown one.

    ``language`` is whatever the caller has: an account's ``language`` (blank means
    "Automatic", which is ``es`` here), the language an email is being written in, or
    nothing at all (an anonymous visitor). It never raises: asking where to ask must
    not be the thing that fails.
    """
    return REQUEST_ACCESS.get(language or "", REQUEST_ACCESS[DEFAULT_LANGUAGE])


def contact_url(language=None):
    """The "Contact us" form in ``language`` — ``es`` for a blank or unknown one.

    The same contract as ``request_access_url``: it never raises, and a language there is no
    form in is the Spanish one.
    """
    return CONTACT.get(language or "", CONTACT[DEFAULT_LANGUAGE])


def browser_language(request):
    """The first language the browser asks for that there is a form in — else ``es``.

    From ``Accept-Language``, by the browser's own order of preference (the ``q``
    values), taking ``ca-ES`` as ``ca``. ``REQUEST_ACCESS`` and ``CONTACT`` speak the same
    three languages, so one answer serves both. Nothing the browser asks for that this
    deployment does not speak (``fr``, ``*``), no header, or one that does not parse, is
    the Spanish form — the same answer ``request_access_url`` gives for an unknown
    language, not Django's ``LANGUAGE_CODE`` (English), which is what
    ``get_language_from_request`` falls back to here and would send a visitor with no
    header to the English form.
    """
    for tag, _quality in parse_accept_lang_header(request.META.get("HTTP_ACCEPT_LANGUAGE", "")):
        language = tag.split("-")[0]
        if language in REQUEST_ACCESS:
            return language
    return DEFAULT_LANGUAGE

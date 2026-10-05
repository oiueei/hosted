"""Where "Request access" lives on this deployment: three forms on Tally.

It used to be a Django page of our own, `/request-access/`, with two free-text questions
and a model row per request. CA moved it to Tally (2026-10-05), as the footer's
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

The addresses are used exactly as written: nothing about the person is added to them.
"""

DEFAULT_LANGUAGE = "es"

REQUEST_ACCESS = {
    "es": "https://tally.so/r/zxaY4M",
    "ca": "https://tally.so/r/D4lz9N",
    "en": "https://tally.so/r/aQ8dPX",
}


def request_access_url(language=None):
    """The "Request access" form in ``language`` — ``es`` for a blank or unknown one.

    ``language`` is whatever the caller has: an account's ``language`` (blank means
    "Automatic", which is ``es`` here), the language an email is being written in, or
    nothing at all (an anonymous visitor). It never raises: asking where to ask must
    not be the thing that fails.
    """
    return REQUEST_ACCESS.get(language or "", REQUEST_ACCESS[DEFAULT_LANGUAGE])

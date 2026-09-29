"""``safe_next_path``: the one door a login's ``next`` has to pass.

A magic link can carry the page the person was heading for when their session ran
out, so the login can send them back to it. That is a redirect built from a value
a client typed, which is exactly the shape of an open redirect: every row of the
tables below is either a same-site path the SPA really has, or one thing a
browser could read as *somewhere else* (another origin, a script, a page that only
loops). The frontend mirrors the same tables in ``nextPath.test.js``.
"""

import pytest

from core.utils import safe_next_path

ACCEPTED = [
    "/collections/AbC123/things/XyZ789",
    "/collections/new",
    "/me/edit",
    "/my-bookings",
    "/AbC123",
    "/collections/AbC123/join?thing=XyZ789",
    # An encoded query value is what ``encodeURIComponent`` produces.
    "/collections/AbC123/things/XyZ789?back=%2Fcollections%2FAbC123",
    "/x" + "a" * 254,  # exactly 256 characters
]

REJECTED = [
    # Another origin, or no path at all.
    "//evil.com",
    "/\\evil.com",
    "https://evil.com",
    "javascript:alert(1)",
    # The SPA's own doors: a loop, or a page with nothing to return to.
    "/login",
    "/login?next=/x",
    "/login/",
    "/LOGIN",
    "/%6Cogin",
    "/logout",
    "/verify/tok",
    "/rsvp/tok",
    "/magic-link/tok",
    # No destination: the login's usual rule is better than Home.
    "/",
    "/?a=1",
    "",
    # Not a string.
    None,
    123,
    ["/me"],
    {"path": "/me"},
    # Characters outside the whitelist.
    "/a b",
    "/a\nb",
    "/me\n",  # ``$`` would let a trailing newline through
    "/x#y",
    "/a:b",
    "/a<b",
    # Traversal, raw or encoded.
    "/../me",
    "/me/..",
    "/%2e%2e/me",
    "/%2E%2E/me",
    # One character over the limit.
    "/x" + "a" * 255,
]


@pytest.mark.parametrize("value", ACCEPTED)
def test_a_same_site_path_the_spa_has_is_returned_untouched(value):
    assert safe_next_path(value) == value


@pytest.mark.parametrize("value", REJECTED)
def test_anything_that_could_leave_the_site_or_loop_is_dropped(value):
    assert safe_next_path(value) == ""

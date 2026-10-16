"""device_class — a request is from a phone or from anything else, or from nobody."""

import pytest
from django.test import RequestFactory

from core.device import device_class

IPHONE = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"
)
ANDROID_CHROME = (
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36"
)
ANDROID_FIREFOX = "Mozilla/5.0 (Android 14; Mobile; rv:127.0) Gecko/127.0 Firefox/127.0"
IPAD = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.5 Safari/605.1.15"
)
ANDROID_TABLET = (
    "Mozilla/5.0 (Linux; Android 14; SM-X710) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
WINDOWS_CHROME = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
WINDOWS_FIREFOX = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0"
WINDOWS_EDGE = WINDOWS_CHROME + " Edg/126.0.0.0"
MAC_SAFARI = IPAD


def request_with(user_agent=None, client_hint=None):
    extra = {}
    if user_agent is not None:
        extra["HTTP_USER_AGENT"] = user_agent
    if client_hint is not None:
        extra["HTTP_SEC_CH_UA_MOBILE"] = client_hint
    return RequestFactory().get("/", **extra)


@pytest.mark.parametrize(
    ("user_agent", "client_hint", "expected"),
    [
        (IPHONE, None, "MOBILE"),
        (ANDROID_CHROME, None, "MOBILE"),
        (ANDROID_FIREFOX, None, "MOBILE"),
        (IPAD, None, "OTHER"),
        (ANDROID_TABLET, None, "OTHER"),
        (WINDOWS_CHROME, None, "OTHER"),
        (WINDOWS_FIREFOX, None, "OTHER"),
        (WINDOWS_EDGE, None, "OTHER"),
        (MAC_SAFARI, None, "OTHER"),
        (WINDOWS_CHROME, "?1", "MOBILE"),
        (ANDROID_CHROME, "?0", "OTHER"),
        (None, None, None),
        ("", None, None),
    ],
    ids=[
        "iphone-safari",
        "android-chrome",
        "android-firefox",
        "ipad-reads-as-a-mac",
        "android-tablet-has-no-mobile",
        "windows-chrome",
        "windows-firefox",
        "windows-edge",
        "mac-safari",
        "client-hint-says-mobile-over-a-desktop-agent",
        "client-hint-says-not-mobile-over-a-phone-agent",
        "no-agent-and-no-hint",
        "empty-agent",
    ],
)
def test_device_class(user_agent, client_hint, expected):
    assert device_class(request_with(user_agent, client_hint)) == expected


def test_a_client_hint_alone_is_enough():
    assert device_class(request_with(None, "?1")) == "MOBILE"
    assert device_class(request_with(None, "?0")) == "OTHER"

"""Which kind of device a request comes from: a phone, or anything else.

Two groups on purpose. A tablet counts as ``OTHER``: an iPad presents itself as a
desktop Safari, so a third group would not be reliable. Nothing is kept from the
request — the answer is a word, and the header it came from is dropped.
"""

MOBILE = "MOBILE"
OTHER = "OTHER"


def device_class(request):
    """``"MOBILE"``, ``"OTHER"``, or ``None`` when the request says nothing.

    ``Sec-CH-UA-Mobile`` (sent by Chromium by default) wins when present: ``?1`` is
    a phone, ``?0`` is not. Otherwise the ``User-Agent`` decides by the rule MDN
    recommends: a ``Mobi`` anywhere in it is a phone.
    """
    hint = request.META.get("HTTP_SEC_CH_UA_MOBILE", "").strip()
    if hint == "?1":
        return MOBILE
    if hint == "?0":
        return OTHER
    user_agent = request.META.get("HTTP_USER_AGENT", "")
    if not user_agent:
        return None
    return MOBILE if "Mobi" in user_agent else OTHER

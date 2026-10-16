"""A deployment's growth-line provider, for the tests of `VIRAL_LINE_PROVIDER`.

`answer` is what the tests swap to make the provider return, or raise, whatever
the case needs; `calls` records who it was asked about.
"""

calls = []

LINE = {"text": "Open <b>yours</b> & share", "cta": "Start <here>", "path": "/stall/new"}


def answer(user, lang):
    return dict(LINE)


def provider(user, lang):
    calls.append((user, lang))
    return answer(user, lang)


not_callable = "this is a string, not a function"

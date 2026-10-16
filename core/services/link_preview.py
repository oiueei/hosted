"""The ``<head>`` a link preview reads, filled in for the pages a stranger may open.

WhatsApp, Telegram, Signal, iMessage and Slack do not run JavaScript: they read the
HTML the server sends. ``spa_index`` serves the same ``index.html`` for every route,
so without this a shared link shows "OIUEEI" and the icon, nothing else.

**The rule: a preview shows only what a visitor with no account could already read
on the page.** A collection or thing is previewed when its own ``can_view(None)``
says so — the model's rule, not a copy of it. Every other page — one that is none of
these routes, and a target that is private, inactive or unknown — gets the site's own
card (``site_preview``; ``og:url`` is the site's root). It is the same bytes whatever
the page, so a private collection cannot be told apart from a code that does not exist.

A collection with no description of its own is described by its kind's sentence
(``kind_what_<KIND>``, the app's own words for it): a card is never only a title.

``share/<token>`` is previewed with the filter ``SharePreviewView`` uses and, like
that endpoint, **with name and description only — never the photo**: the card must
not give a holder of the link more than the join page does.
"""

import re

from django.utils.html import escape

from core.models import Collection, Thing
from core.services.email_texts import T
from core.utils import asset_url, resolve_localized

# The address of a collection's page: one prefix per kind, and the pre-kind one
# (an unknown code reaches the SPA under it, and previews nothing).
PREVIEW_COLLECTION_PREFIXES = ("collections", "stall", "library", "shed")

DESCRIPTION_LIMIT = 200
SITE_NAME = "OIUEEI"

_SEGMENT = r"([^/]+)"
_THING_ROUTES = (
    re.compile(r"things/" + _SEGMENT),
    re.compile(r"(?:" + "|".join(PREVIEW_COLLECTION_PREFIXES) + r")/[^/]+/things/" + _SEGMENT),
)
_SHARE_ROUTE = re.compile(r"share/" + _SEGMENT)

_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+", re.MULTILINE)
_LIST_MARK = re.compile(r"^\s*(?:[-*+]|\d+\.)\s+", re.MULTILINE)
_EMPHASIS = re.compile(r"\*\*|__|\*|(?<!\w)_|_(?!\w)")
_TABLE_RULE = re.compile(r"^\s*\|?(?:\s*:?-{3,}:?\s*\|?)+\s*$", re.MULTILINE)
_TITLE = re.compile(r"<title>.*?</title>", re.IGNORECASE | re.DOTALL)


def plain_description(markdown, limit=DESCRIPTION_LIMIT):
    """One line of plain text out of a Markdown description, cut at a word."""
    text = _LINK.sub(r"\1", markdown or "")
    text = _TABLE_RULE.sub("", text)
    text = _HEADING.sub("", text)
    text = _LIST_MARK.sub("", text)
    text = _EMPHASIS.sub("", text)
    text = text.replace("|", " ")
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text[:limit]
    if text[limit] != " ":
        cut = cut.rsplit(" ", 1)[0] if " " in cut else cut
    return cut.rstrip(" ,.;:-") + "…"


def _preview(source, lang, with_image):
    title = resolve_localized(source.headline, lang)
    return {
        "title": title,
        "description": plain_description(resolve_localized(source.description, lang)),
        "image": asset_url(source.thumbnail) if with_image else None,
    }


def _collection_preview(collection, with_image):
    """A collection's card: its own description, or — when it has none in the
    language of the reader — the sentence of its kind, so a card is never only a
    title. The sentence says what the kind is and nothing about this group, which
    the join page already tells anyone holding the link."""
    lang = collection.language or None
    card = _preview(collection, lang, with_image)
    if not card["description"]:
        card["description"] = T(f"kind_what_{collection.kind}", lang)
    return card


def site_preview():
    """The card of every page that has none of its own: what OIUEEI is, in the
    deployment's language. No database, no photo, and nothing that depends on the
    page, so a private collection and a code that names nothing get the same one."""
    return {"title": SITE_NAME, "description": T("generic_parent_pitch"), "image": None}


def route_for_preview(path):
    """What a path would look up for a preview, or ``None`` — **without touching the
    database**: ``("collection", code)``, ``("thing", code)`` or ``("share", token)``.

    A ``None`` is a route that was never going to ask anything, which is what lets a
    caller count only the visits that will.
    """
    route = path.strip("/")
    parts = route.split("/")
    if parts[0] in PREVIEW_COLLECTION_PREFIXES and (
        len(parts) == 2 or (len(parts) == 3 and parts[2] == "join")
    ):
        return "collection", parts[1]
    for pattern in _THING_ROUTES:
        match = pattern.fullmatch(route)
        if match:
            return "thing", match.group(1)
    match = _SHARE_ROUTE.fullmatch(route)
    if match:
        return "share", match.group(1)
    return None


def preview_for_route(route):
    """``{"title", "description", "image"}`` for a route from ``route_for_preview``
    that a stranger may preview, else ``None``. This is where the queries are."""
    kind, key = route
    if kind == "collection":
        collection = Collection.objects.filter(code=key).first()
        if collection is None or not collection.can_view(None):
            return None
        return _collection_preview(collection, with_image=True)
    if kind == "thing":
        thing = Thing.objects.filter(code=key).first()
        if thing is None or not thing.can_view(None):
            return None
        home = thing.collections.first()
        return _preview(thing, (home.language if home else "") or None, with_image=True)
    collection = Collection.objects.filter(share_token=key, status=Collection.Status.ACTIVE).first()
    if collection is None:
        return None
    return _collection_preview(collection, with_image=False)


def inject_preview(html, preview, url):
    """``html`` with the title and the Open Graph tags of ``preview`` filled in.

    Every value is escaped: they are an owner's words inside HTML attributes. An
    ``index.html`` without ``<title>`` or ``</head>`` comes back as it was.
    """
    if not _TITLE.search(html) or "</head>" not in html:
        return html
    title = escape(preview["title"])
    description = escape(preview["description"])
    image = preview["image"]
    tags = []
    if description:
        tags.append(f'<meta name="description" content="{description}">')
        tags.append(f'<meta property="og:description" content="{description}">')
    tags += [
        f'<meta property="og:title" content="{title}">',
        f'<meta property="og:site_name" content="{SITE_NAME}">',
        '<meta property="og:type" content="website">',
        f'<meta property="og:url" content="{escape(url)}">',
    ]
    if image:
        tags.append(f'<meta property="og:image" content="{escape(image)}">')
    tags.append(
        f'<meta name="twitter:card" content="{"summary_large_image" if image else "summary"}">'
    )
    page_title = title if preview["title"] == SITE_NAME else f"{title} — {SITE_NAME}"
    html = _TITLE.sub(lambda _: f"<title>{page_title}</title>", html, count=1)
    return html.replace("</head>", "".join(tags) + "</head>", 1)

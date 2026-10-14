"""The ``<head>`` a link preview reads, filled in for the pages a stranger may open.

WhatsApp, Telegram, Signal, iMessage and Slack do not run JavaScript: they read the
HTML the server sends. ``spa_index`` serves the same ``index.html`` for every route,
so without this a shared link shows "OIUEEI" and the icon, nothing else.

**The rule: a preview shows only what a visitor with no account could already read
on the page.** A collection or thing is previewed when its own ``can_view(None)``
says so — the model's rule, not a copy of it. A private, inactive or unknown
target gets ``None``, and the caller then serves ``index.html`` untouched, byte for
byte, so a private collection cannot be told apart from a code that does not exist.

``share/<token>`` is previewed with the filter ``SharePreviewView`` uses and, like
that endpoint, **with name and description only — never the photo**: the card must
not give a holder of the link more than the join page does.
"""

import re

from django.utils.html import escape

from core.models import Collection, Thing
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


def preview_for_path(path):
    """``{"title", "description", "image"}`` for a path a stranger may preview, else ``None``.

    No query at all unless the path is one of the routes in the module docstring.
    """
    route = path.strip("/")
    parts = route.split("/")
    if parts[0] in PREVIEW_COLLECTION_PREFIXES and (
        len(parts) == 2 or (len(parts) == 3 and parts[2] == "join")
    ):
        collection = Collection.objects.filter(code=parts[1]).first()
        if collection is None or not collection.can_view(None):
            return None
        return _preview(collection, collection.language or None, with_image=True)

    for pattern in _THING_ROUTES:
        match = pattern.fullmatch(route)
        if match:
            thing = Thing.objects.filter(code=match.group(1)).first()
            if thing is None or not thing.can_view(None):
                return None
            home = thing.collections.first()
            return _preview(thing, (home.language if home else "") or None, with_image=True)

    match = _SHARE_ROUTE.fullmatch(route)
    if match:
        collection = Collection.objects.filter(
            share_token=match.group(1), status=Collection.Status.ACTIVE
        ).first()
        if collection is None:
            return None
        return _preview(collection, collection.language or None, with_image=False)
    return None


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
    html = _TITLE.sub(lambda _: f"<title>{title} — {SITE_NAME}</title>", html, count=1)
    return html.replace("</head>", "".join(tags) + "</head>", 1)

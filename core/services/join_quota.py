"""The daily cap on how many people one collection may be joined by.

`POST /auth/join/` mails a magic link to whatever address is typed into it, and
neither door that reaches it is a secret: a PUBLIC collection's `collection_code`
is in that collection's own URL, and a share token is handed out precisely so
that people pass it around. So **anyone can ask this deployment to send mail to
anyone**, which is a spam relay pointed at the operator's own sending domain —
unsolicited mail arriving from it, complaints filed against it, and in the end
every genuine magic link landing in a spam folder.

The view's rate limits do not close this, and were never meant to. They cap how
often **one IP** asks (5/min) and how often **one victim** is mailed (5/hour) —
nothing about a hundred addresses being mailed once each, which is the shape of
the attack. And `INVITE_EMAILS_PER_DAY`, the setting that exists for exactly
this reputation concern, counts only what an *account* sends through the owner's
invite routes: the one door needing no account at all was the one nobody counted.

**Keyed by collection.** Not by IP — that is what already failed. Not by
deployment either, tempting as it looks: one abused collection would then deny
every other collection its joins, handing the attacker a denial of service
against the whole instance. Per collection, abusing a group's public code costs
that group its own day's allowance and nothing else.

**Off unless the operator sets a number**, like every other abuse guard here.
Only they know what their provider tolerates — and a share link pasted into a
WhatsApp group can legitimately bring two hundred people in one evening, which
the standalone has no business calling abuse.

Each join sends one magic link, and a **first** join also sends the collection's
welcome document when the owner set one, so the mail this permits is at most
twice the number configured. It is a cap on joins because that is the event
worth counting; the emails follow from it.
"""

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

# ~24h. The date is in the key, so the window rolls over on its own; the TTL is
# only there to stop yesterday's keys accumulating in the cache table.
_JOIN_QUOTA_TTL = 60 * 60 * 24


def _join_quota_cap():
    """Today's allowance, or ``None`` when the cap is off.

    Off means either the whole rate-limiting layer is disabled (dev, tests) or
    the operator left it unset/zero — the standalone default. Same two switches
    as ``INVITE_EMAILS_PER_DAY``, deliberately: an operator turning limits off
    should not have to find two places to do it.
    """
    if not getattr(settings, "RATELIMIT_ENABLE", True):
        return None
    cap = getattr(settings, "COLLECTION_JOINS_PER_DAY", 0) or 0
    return cap if cap > 0 else None


def _join_quota_key(collection_code):
    return f"joinq:{collection_code}:{timezone.localdate().isoformat()}"


def join_quota_exhausted(collection_code):
    """Whether this collection has already taken today's joins.

    Read-then-set on a DatabaseCache is not atomic (see the I7 note in
    ``config/settings/base.py``), so a burst can slip a few past the line. That
    is the same trade-off every counter here makes and the right one: this is
    coarse abuse prevention protecting a sending reputation, not a quota anyone
    is billed against.
    """
    cap = _join_quota_cap()
    if cap is None:
        return False
    return cache.get(_join_quota_key(collection_code), 0) >= cap


def consume_join_quota(collection_code):
    """Record one join against today's allowance."""
    if _join_quota_cap() is None:
        return
    key = _join_quota_key(collection_code)
    cache.set(key, cache.get(key, 0) + 1, _JOIN_QUOTA_TTL)

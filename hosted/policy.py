"""What this deployment lets an account create, before and after vetting.

Upstream says yes to everything (`OpenCreatorPolicy`), which is OIUEEI as a
product. Here the line falls between **what only costs the person offering it**
and **what puts somebody else on the hook**:

- Giving and selling are open. Whatever happens, it happens once and ends there.
- A COMMUNITY collection lets strangers add things to a group under someone's
  name, and lending or renting means a thing has to come back. Both create an
  obligation to a third party, and both are what this deployment reads a
  sentence about a person before handing out.

The narrowing is not a claim that people are untrustworthy. It is that the
operator answers for what this service is used for, and cannot answer for what
they have never been told.
"""

from django.urls import NoReverseMatch, reverse

from core.models import Collection, Thing
from core.services.creator_policy import Capabilities, CreatorPolicy

from .models import CreatorValidation

# Available to anyone with an account, no questions asked.
OPEN_MODES = (Collection.Mode.PROPRIETARY,)
OPEN_TYPES = (Thing.Type.GIFT_THING, Thing.Type.SELL_THING)


class HostedCreatorPolicy(CreatorPolicy):
    """Vetted people get the whole product; everyone else gets the open half."""

    def capabilities(self, user) -> Capabilities:
        if self._is_validated(user):
            return Capabilities(
                collection_modes=tuple(Collection.Mode.values),
                thing_types=tuple(Thing.Type.values),
            )
        return Capabilities(
            collection_modes=OPEN_MODES,
            thing_types=OPEN_TYPES,
            request_url=request_access_url(),
        )

    @staticmethod
    def _is_validated(user):
        """Whether this person has been approved, asking the database once.

        The policy instance is cached and shared across requests, so it must
        stay stateless — but the `user` is built fresh per request, which makes
        it the right place to hang the answer. Without this the flag is looked up
        two or three times in a single create: `collection_mode_denial` asks
        `allows_*` and then reads `request_url` off a second `capabilities()`
        call.
        """
        if not getattr(user, "is_authenticated", False):
            return False
        cached = getattr(user, "_hosted_validation_approved", None)
        if cached is None:
            cached = CreatorValidation.objects.filter(
                user=user, status=CreatorValidation.Status.APPROVED
            ).exists()
            user._hosted_validation_approved = cached
        return cached


def request_access_url():
    """Where somebody goes to ask — the form this app serves.

    A site-relative path, deliberately: the form is a Django page served by the
    same deployment as the SPA that links it, so a relative link is correct
    everywhere the app runs — localhost, a review app, production — with nothing
    to configure and nothing to get wrong.

    Resolved rather than hard-coded so the route can move without the copy in
    two 403 bodies and one React component going stale. It falls back to the
    canonical path when the URLconf is not mounted (a bare `manage.py shell`, a
    test overriding ROOT_URLCONF): serving a capability list with a guessed link
    beats 500ing `/auth/me/` over a URL name.
    """
    try:
        return reverse("hosted:request-access")
    except NoReverseMatch:
        return "/request-access/"

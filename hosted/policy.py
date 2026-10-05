"""What this deployment lets an account create, before and after vetting.

Upstream says yes to everything (`OpenCreatorPolicy`), which is OIUEEI as a
product. Here the line falls between **what only costs the person offering it**
and **what puts somebody else on the hook**:

- Giving and selling are open. Whatever happens, it happens once and ends there.
- A COMMUNITY collection lets strangers add things to a group under someone's
  name; lending or renting means a thing has to come back; a reservation
  commits the operator's own premises to a stranger for a day. Each creates an
  obligation to a third party, and each is what this deployment reads a
  sentence about a person before handing out. (RESERVE_THING is withheld the
  same way — it is simply absent from `OPEN_TYPES` below, so an unvetted
  account never sees the verb.)

The narrowing is not a claim that people are untrustworthy. It is that the
operator answers for what this service is used for, and cannot answer for what
they have never been told.
"""

from core.models import Collection, Thing
from core.services.creator_policy import Capabilities, CreatorPolicy

from .models import CreatorValidation
from .tally import request_access_url

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
            # The form of the account's own language (blank = Automatic = `es`; an
            # anonymous visitor has none). This is what the two 403 bodies that say
            # where to ask carry too — core builds them from this very value.
            request_url=request_access_url(getattr(user, "language", "")),
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

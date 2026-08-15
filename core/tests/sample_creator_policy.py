"""A narrower `CreatorPolicy`, named by the tests through `CREATOR_POLICY`.

Not a test module — pytest only collects `test_*` — but the *input* to several:
the setting takes a dotted path to a real importable class, so proving that a
deployment can narrow the product needs a real narrowing to point at.

It is deliberately the shape a service operator would write: the two things
that carry obligations to someone else — a collection anyone can add to, and a
thing that has to come back — are the ones held behind a request, while giving
and selling stay open. The standalone ships nothing like this, and that is the
point: everything here has to work without a line of it living in `core`.
"""

from core.models import Collection, Thing
from core.services.creator_policy import Capabilities, CreatorPolicy

REQUEST_URL = "https://example.test/request-access/"


class RestrictedCreatorPolicy(CreatorPolicy):
    """COMMUNITY, LEND and RENT are held back; the rest is open."""

    def capabilities(self, user) -> Capabilities:
        return Capabilities(
            collection_modes=(Collection.Mode.PROPRIETARY,),
            thing_types=(Thing.Type.GIFT_THING, Thing.Type.SELL_THING),
            request_url=REQUEST_URL,
        )


class SilentlyRestrictedCreatorPolicy(RestrictedCreatorPolicy):
    """The same, minus anywhere to ask — a deployment that just says no."""

    def capabilities(self, user) -> Capabilities:
        return Capabilities(
            collection_modes=(Collection.Mode.PROPRIETARY,),
            thing_types=(Thing.Type.GIFT_THING, Thing.Type.SELL_THING),
            request_url=None,
        )

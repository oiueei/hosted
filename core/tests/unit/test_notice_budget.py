"""Every notice type says whether it asks for an action or only informs.

A new ``InAppNotification.Type`` that nobody classified would be folded away (or
kept in the way) by accident; this table makes the decision happen when the type
is made.
"""

import pytest

from core.models import User
from core.models.notification import InAppNotification

Type = InAppNotification.Type

ASKS_FOR_AN_ACTION = {
    Type.BOOKING_REQUESTED,
    Type.FAQ_QUESTION,
    Type.INVITE_PROPOSED,
    Type.THING_REPORTED,
}
# Types the team's requests-and-reservations group takes (BOOKING_REQUESTED is also
# there, but it asks for an action first). RESERVATION_CANCELLED only some copies.
TEAM_GROUP = {Type.BOOKING_DECIDED, Type.RESERVATION_MADE, Type.RESERVATION_CANCELLED}
ONLY_INFORM = {
    Type.BROADCAST,
    Type.COLLECTION_DELETED,
    Type.COLLECTION_REVOKED,
    Type.BOOKING_ACCEPTED,
    Type.BOOKING_REJECTED,
    Type.FAQ_ANSWERED,
    Type.FAQ_HIDDEN,
    Type.INVITE_REJECTED,
    Type.MEMBER_LEFT,
    Type.INVITE_PROPOSAL_APPROVED,
    Type.INVITE_PROPOSAL_DECLINED,
    Type.PROMOTED_CO_OWNER,
    Type.DEMOTED_CO_OWNER,
}


def test_every_notice_type_is_decided_exactly_once():
    everything = set(Type)
    buckets = [ASKS_FOR_AN_ACTION, TEAM_GROUP, ONLY_INFORM]

    assert set().union(*buckets) == everything, "a notice type nobody decided"
    assert sum(len(b) for b in buckets) == len(everything), "a type decided twice"


def test_the_model_holds_the_same_list_of_actions():
    assert {Type(t) for t in InAppNotification.ACTION_NOTICE_TYPES} == ASKS_FOR_AN_ACTION


@pytest.mark.django_db
def test_the_informative_set_is_what_the_table_says():
    user = User.objects.create(code="LALA01", email="lala@your-domain.test")
    for kind in Type:
        # A cancellation told to the member whose reservation was cancelled informs.
        payload = {"cancelled_by_owner": True} if kind == Type.RESERVATION_CANCELLED else {}
        InAppNotification.objects.create(user=user, type=kind, payload=payload)

    informative = set(InAppNotification.informative_notices().values_list("type", flat=True))

    assert informative == ONLY_INFORM | {Type.RESERVATION_CANCELLED}

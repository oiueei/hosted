"""One week of the series, derived from fabricated events (`hosted/metrics.py`).

**Tests code that is not in the standalone** (see `test_hosted_popin.py` for why the
file sits here).

Every event carries an explicit `created`, in Madrid time, so each test reads as a small
story: who did what on which day. Pinned: where a week begins and ends (across both
clock changes), what is excluded as demo, that people stay in the history after leaving,
the stocks, the stages of the cycle and their order, generations through a deleted
collection, requests apart from reservations, the medians and the shape of the catalogue.
"""

from datetime import UTC, date, timedelta

import pytest

from core.models import Collection, DailyActivity, Event, Thing, User
from core.tests.unit.hosted_story import (
    LALA,
    adds,
    asks,
    creates,
    joins,
    log,
    madrid,
    person,
)
from hosted.metrics import (
    LIVE_ONLY_KEYS,
    METRIC_KEYS,
    SEED_COLLECTION_CODES,
    SEED_THING_CODES,
    WEEK_TZ,
    _History,
    cohorts_as_of,
    generation_k,
    snapshot_metrics,
    week_bounds,
)
from hosted.models import CreatorValidation

K = Event.Kind
W37 = date(2026, 9, 7)  # Monday of the first week
W38 = date(2026, 9, 14)
W39 = date(2026, 9, 21)
W40 = date(2026, 9, 28)

A, B, C, D = "AAAAAA", "BBBBBB", "CCCCCC", "DDDDDD"


def week(start, **kw):
    return snapshot_metrics(start, **kw)


@pytest.fixture
def onboarding(db):
    owner = User.objects.create(code="ONBOWN", email="lala@your-domain.test")
    return Collection.objects.create(
        code="ONBCOL", owner=owner, headline="Demo", is_onboarding=True
    )


@pytest.mark.django_db
class TestWhereAWeekBegins:
    def test_sunday_night_in_madrid_in_summer_time_belongs_to_the_week_that_closes(self):
        # 23:30 in Madrid on Sunday 13 Sep is 21:30 UTC (UTC+2).
        creates(A, "COL001", madrid(date(2026, 9, 13), 23, 30))
        creates(B, "COL002", madrid(date(2026, 9, 14), 0, 30))

        assert week(W37)["collections_created"] == 1
        assert week(W38)["collections_created"] == 1

    def test_the_week_that_holds_the_clock_change_takes_the_sunday_night_in(self):
        # Sunday 25 Oct 2026 is the change back to winter time; 23:30 is then 22:30 UTC.
        monday = date(2026, 10, 19)
        creates(A, "COL001", madrid(date(2026, 10, 25), 23, 30))
        creates(B, "COL002", madrid(date(2026, 10, 26), 0, 30))

        assert week(monday)["collections_created"] == 1
        assert week(date(2026, 10, 26))["collections_created"] == 1

    def test_the_bounds_are_two_mondays_at_midnight_in_madrid(self):
        start, cutoff = week_bounds(W37)

        assert start.astimezone(WEEK_TZ).isoformat() == "2026-09-07T00:00:00+02:00"
        assert cutoff.astimezone(WEEK_TZ).isoformat() == "2026-09-14T00:00:00+02:00"
        # Compared as instants: the week of the clock change is an hour longer in real time.
        assert cutoff.astimezone(UTC) - start.astimezone(UTC) == timedelta(days=7)
        winter_start, winter_cutoff = week_bounds(date(2026, 10, 19))
        assert winter_cutoff.astimezone(UTC) - winter_start.astimezone(UTC) == timedelta(
            days=7, hours=1
        )


@pytest.mark.django_db
class TestWhatIsExcludedAsDemo:
    def test_a_seed_character_an_onboarding_collection_and_the_open_door_move_nothing(
        self, onboarding
    ):
        seed = "La1aN1"
        on = madrid(date(2026, 9, 8))
        creates(seed, "SEEDCO", on)
        joins(B, onboarding.code, on, source=Event.Source.ONBOARDING)
        joins(C, onboarding.code, on, source=Event.Source.INVITE)
        adds(C, "DEMOTH", onboarding.code, on)
        asks(D, "DEMOTH", on)  # a request on a thing added in onboarding
        log(K.THING_REMOVED, C, on, thing="DEMOTH")

        got = week(W37)

        for key in (
            "new_people",
            "creators",
            "guests",
            "collections",
            "memberships",
            "things",
            "things_added",
            "things_removed",
            "requests",
            "requests_gift",
            "collections_created",
        ):
            assert got[key] == 0, key

    def test_a_guest_who_left_their_group_afterwards_still_counts_in_the_week_they_were_one(self):
        creates(A, "COL001", madrid(date(2026, 9, 8)))
        joins(B, "COL001", madrid(date(2026, 9, 9)))
        log(K.MEMBER_LEFT, B, madrid(date(2026, 9, 16)), collection="COL001")

        assert week(W37)["guests"] == 1
        assert week(W37)["new_people"] == 2  # A and B
        assert week(W38)["guests"] == 0
        assert week(W38)["new_people"] == 0

    def test_an_account_that_only_visited_through_the_open_door_is_not_a_new_person(self):
        log(K.USER_JOINED, B, madrid(date(2026, 9, 8)))

        assert week(W37)["new_people"] == 0


@pytest.mark.django_db
class TestTheOperatorsOwnAccountsCount:
    def test_an_owner_with_no_earlier_join_is_a_seeded_creator_of_generation_zero(self):
        creates(A, "COL001", madrid(date(2026, 9, 8)))

        got = week(W37)

        assert got["creators"] == 1
        assert got["creators_seeded"] == 1
        assert got["creators_organic"] == 0
        assert got["owners_gen0"] == 1
        assert got["cycle_entered"] == 0


@pytest.mark.django_db
class TestGenerations:
    def test_it_follows_the_owner_of_a_collection_that_has_since_been_deleted(self):
        creates(A, "COL001", madrid(date(2026, 9, 8)))
        joins(B, "COL001", madrid(date(2026, 9, 9)))
        creates(B, "COL002", madrid(date(2026, 9, 10)))
        log(K.COLLECTION_DELETED, A, madrid(date(2026, 9, 11)), collection="COL001")
        joins(D, "COL002", madrid(date(2026, 9, 12)))
        creates(D, "COL003", madrid(date(2026, 9, 13)))

        got = week(W37)
        rows = generation_k(week_bounds(W37)[1])

        assert (got["owners_gen0"], got["owners_gen1"], got["owners_gen2plus"]) == (1, 1, 1)
        assert rows[0]["owners"] == 1 and rows[0]["next_owners"] == 1 and rows[0]["k"] == 1
        assert rows[0]["brought"] == 1 and rows[0]["converted"] == 1
        assert rows[1]["next_owners"] == 1

    def test_a_parent_whose_creation_is_not_in_the_log_counts_as_generation_zero(self):
        joins(B, "GHOST1", madrid(date(2026, 9, 9)))
        creates(B, "COL002", madrid(date(2026, 9, 10)))

        got = week(W37)

        assert got["owners_gen1"] == 1
        assert got["owners_gen0"] == 0
        # With nobody in generation 0 the table starts at the first one there is.
        rows = generation_k(week_bounds(W37)[1])
        assert [(r["generation"], r["owners"]) for r in rows] == [(1, 1)]

    def test_the_two_factors_of_k_are_brought_per_owner_and_the_share_who_became_owners(self):
        creates(A, "COL001", madrid(date(2026, 9, 8)))
        for guest in (B, C, D):
            joins(guest, "COL001", madrid(date(2026, 9, 9)))
        creates(B, "COL002", madrid(date(2026, 9, 10)))

        row = generation_k(week_bounds(W37)[1])[0]

        assert (row["owners"], row["brought"], row["converted"], row["next_owners"]) == (1, 3, 1, 1)
        assert row["k"] == pytest.approx((3 / 1) * (1 / 3))


@pytest.mark.django_db
class TestTheStagesOfTheCycle:
    def test_somebody_who_creates_without_returning_or_asking_is_an_owner_and_not_a_returner(self):
        creates(A, "COL001", madrid(date(2026, 9, 8)))
        joins(B, "COL001", madrid(date(2026, 9, 9)))
        creates(B, "COL002", madrid(date(2026, 9, 10)))

        got = week(W37)

        assert got["cycle_entered"] == 1
        assert got["cycle_owner"] == 1
        assert got["cycle_returned"] == 0
        assert got["cycle_requested"] == 0

    def test_returning_is_a_second_distinct_day_of_activity_from_the_day_they_entered(self):
        creates(A, "COL001", madrid(date(2026, 9, 8)))
        joins(B, "COL001", madrid(date(2026, 9, 9)))
        joins(C, "COL001", madrid(date(2026, 9, 9)))
        user_b, user_c = person(B), person(C)
        for day in (date(2026, 9, 9), date(2026, 9, 11)):
            DailyActivity.objects.create(user=user_b, date=day)
        DailyActivity.objects.create(user=user_c, date=date(2026, 9, 9))
        DailyActivity.objects.create(user=user_c, date=date(2026, 9, 3))  # before entering

        assert week(W37)["cycle_returned"] == 1

    def test_a_request_is_the_stage_whether_it_is_a_hold_or_a_reservation(self):
        creates(A, "COL001", madrid(date(2026, 9, 8)))
        joins(B, "COL001", madrid(date(2026, 9, 9)))
        asks(B, "THG001", madrid(date(2026, 9, 10)), type="RESERVE_THING")

        assert week(W37)["cycle_requested"] == 1

    def test_the_first_thing_must_come_after_the_collection_it_belongs_to(self):
        creates(A, "COL001", madrid(date(2026, 9, 8)))
        joins(B, "COL001", madrid(date(2026, 9, 9)))
        adds(B, "THG001", "COL001", madrid(date(2026, 9, 9)))  # a member's contribution, earlier
        creates(B, "COL002", madrid(date(2026, 9, 10)))
        adds(B, "THG002", "COL002", madrid(date(2026, 9, 11)))

        assert week(W37)["cycle_first_thing"] == 1
        assert week(W37)["cycle_owner"] == 1

    def test_closing_the_loop_needs_somebody_else_joining_a_collection_of_theirs(self):
        creates(A, "COL001", madrid(date(2026, 9, 8)))
        joins(B, "COL001", madrid(date(2026, 9, 9)))
        creates(B, "COL002", madrid(date(2026, 9, 10)))
        joins(B, "COL002", madrid(date(2026, 9, 10), 13))  # the owner in their own collection

        assert week(W37)["cycle_closed"] == 0

        joins(C, "COL002", madrid(date(2026, 9, 11)))

        assert week(W37)["cycle_closed"] == 1

    def test_the_funnel_accumulates_week_after_week(self):
        creates(A, "COL001", madrid(date(2026, 9, 8)))
        joins(B, "COL001", madrid(date(2026, 9, 9)))
        creates(B, "COL002", madrid(date(2026, 9, 17)))

        assert week(W37)["cycle_owner"] == 0
        assert week(W38)["cycle_owner"] == 1
        assert week(W38)["cycle_entered"] == 1


@pytest.mark.django_db
class TestStocksAtTheCutoff:
    def test_a_membership_that_is_joined_left_and_joined_again_is_one_zero_one(self):
        creates(A, "COL001", madrid(date(2026, 9, 8)))
        joins(B, "COL001", madrid(date(2026, 9, 9)))
        log(K.MEMBER_LEFT, B, madrid(date(2026, 9, 16)), collection="COL001")
        joins(B, "COL001", madrid(date(2026, 9, 23)))

        assert [week(w)["memberships"] for w in (W37, W38, W39)] == [1, 0, 1]

    def test_a_thing_leaves_the_stock_the_week_it_is_removed(self):
        creates(A, "COL001", madrid(date(2026, 9, 8)))
        adds(A, "THG001", "COL001", madrid(date(2026, 9, 9)), type="LEND_THING")
        log(K.THING_REMOVED, A, madrid(date(2026, 9, 16)), thing="THG001")

        assert week(W37)["things"] == 1
        assert week(W37)["things_lend"] == 1
        assert week(W38)["things"] == 0
        assert week(W38)["things_lend"] == 0
        assert week(W38)["things_removed"] == 1

    def test_a_deleted_collection_takes_its_memberships_and_its_creator_with_it(self):
        creates(A, "COL001", madrid(date(2026, 9, 8)))
        joins(B, "COL001", madrid(date(2026, 9, 9)))
        log(K.COLLECTION_DELETED, A, madrid(date(2026, 9, 16)), collection="COL001")

        got = week(W38)

        assert (got["collections"], got["memberships"], got["creators"], got["guests"]) == (
            0,
            0,
            0,
            0,
        )

    def test_somebody_who_runs_one_group_and_belongs_to_another_is_a_creator_not_a_guest(self):
        creates(A, "COL001", madrid(date(2026, 9, 8)))
        creates(B, "COL002", madrid(date(2026, 9, 8)))
        joins(B, "COL001", madrid(date(2026, 9, 9)))

        got = week(W37)

        assert got["creators"] == 2
        assert got["guests"] == 0
        assert got["memberships"] == 1

    def test_each_verb_has_its_own_stock(self):
        creates(A, "COL001", madrid(date(2026, 9, 8)))
        for i, verb in enumerate(
            ("GIFT_THING", "SELL_THING", "LEND_THING", "RENT_THING", "RESERVE_THING")
        ):
            adds(A, f"THG00{i}", "COL001", madrid(date(2026, 9, 9)), type=verb)

        got = week(W37)

        assert [got[k] for k in ("things_gift", "things_sell", "things_lend", "things_rent")] == [
            1,
            1,
            1,
            1,
        ]
        assert got["things_reserve"] == 1
        assert got["things"] == 5


@pytest.mark.django_db
class TestRequestsAndReservationsAreSeparate:
    def test_requests_are_the_four_verbs_and_reservations_are_counted_apart(self):
        on = madrid(date(2026, 9, 9))
        for i, verb in enumerate(("GIFT_THING", "SELL_THING", "LEND_THING", "RENT_THING")):
            asks(B, f"THG00{i}", on, type=verb)
        asks(B, "THG009", on, type="RESERVE_THING")
        asks(B, "THG009", on, type="RESERVE_THING")

        got = week(W37)

        assert got["requests"] == 4
        assert [got[f"requests_{v}"] for v in ("gift", "sell", "lend", "rent")] == [1, 1, 1, 1]
        assert got["reservations"] == 2

    def test_accepted_counts_the_four_verbs_and_leaves_the_self_confirming_reservations_out(self):
        on = madrid(date(2026, 9, 9))
        log(K.HOLD_ACCEPTED, B, on, thing="THG001", type="LEND_THING")
        log(K.HOLD_ACCEPTED, B, on, thing="THG002", type="RESERVE_THING")

        assert week(W37)["requests_accepted"] == 1


@pytest.mark.django_db
class TestJoinsByDoorAndTheOperatorsLedger:
    def test_each_door_has_a_column_and_a_blank_source_is_unknown(self):
        on = madrid(date(2026, 9, 9))
        creates(A, "COL001", on)
        joins(B, "COL001", on, source=Event.Source.INVITE)
        joins(C, "COL001", on, source=Event.Source.SHARE)
        joins(D, "COL001", on, source=Event.Source.PUBLIC)
        joins("EEEEEE", "COL001", on, source=Event.Source.RECOMMENDATION)
        joins("FFFFFF", "COL001", on, source="")

        got = week(W37)

        assert [got[k] for k in ("joins_invite", "joins_share", "joins_public")] == [1, 1, 1]
        assert got["joins_recommendation"] == 1
        assert got["joins_unknown"] == 1

    def test_validations_asked_and_approved_in_the_week(self):
        user = User.objects.create(code=B, email="lele@your-domain.test")
        other = User.objects.create(code=C, email="lili@your-domain.test")
        asked = CreatorValidation.objects.create(
            user=user, who="x", intent="y", created=madrid(date(2026, 9, 8))
        )
        asked.status = CreatorValidation.Status.APPROVED
        asked.resolved = madrid(date(2026, 9, 16))
        asked.save()
        CreatorValidation.objects.create(
            user=other, who="x", intent="y", created=madrid(date(2026, 9, 16))
        )

        assert week(W37)["validations_requested"] == 1
        assert week(W37)["validations_approved"] == 0
        assert week(W38)["validations_requested"] == 1
        assert week(W38)["validations_approved"] == 1

    def test_active_people_are_split_by_their_role_at_the_cutoff(self):
        creates(A, "COL001", madrid(date(2026, 9, 8)))
        joins(B, "COL001", madrid(date(2026, 9, 9)))
        for code in (A, B):
            user = person(code)
            DailyActivity.objects.create(user=user, date=date(2026, 9, 10))
        stranger = person(C)
        DailyActivity.objects.create(user=stranger, date=date(2026, 9, 10))
        DailyActivity.objects.create(user=stranger, date=date(2026, 9, 14))  # next week

        got = week(W37)

        assert (got["active_creators"], got["active_guests"]) == (1, 1)


@pytest.mark.django_db
class TestTheMedians:
    def _owner_after(self, who, days, collection):
        """`who` joins A's group on 8 Sep and creates their own `days` later."""
        joins(who, "COL001", madrid(date(2026, 9, 8)))
        creates(who, collection, madrid(date(2026, 9, 8) + timedelta(days=days)))

    def test_there_is_no_median_without_samples(self):
        creates(A, "COL001", madrid(date(2026, 9, 8)))

        got = week(W37)

        assert got["cycle_median_days_to_owner"] is None
        assert got["owner_median_days_to_first_request"] is None

    @pytest.mark.parametrize(
        "delays, median",
        [([2], 2), ([1, 5], 3), ([1, 3, 9], 3)],
        ids=["one sample", "two samples", "three samples"],
    )
    def test_the_time_to_become_an_owner_is_a_median_not_a_mean(self, delays, median):
        creates(A, "COL001", madrid(date(2026, 9, 7)))
        for who, days, code in zip((B, C, D), delays, ("COL00B", "COL00C", "COL00D"), strict=False):
            self._owner_after(who, days, code)

        assert week(W38)["cycle_median_days_to_owner"] == median

    def test_the_time_to_the_first_request_received_is_measured_on_a_thing_of_their_own(self):
        creates(A, "COL001", madrid(date(2026, 9, 7)))
        self._owner_after(B, 1, "COL00B")  # owner on 9 Sep 12:00
        adds(B, "THG001", "COL00B", madrid(date(2026, 9, 10)))
        asks(C, "THG001", madrid(date(2026, 9, 12)))  # three days after
        asks(C, "THG001", madrid(date(2026, 9, 13)))
        asks(C, "OTHER1", madrid(date(2026, 9, 9)))  # a request on somebody else's thing

        assert week(W37)["owner_median_days_to_first_request"] == 3


@pytest.mark.django_db
class TestTheCohortTriangle:
    def test_a_window_is_shown_only_once_it_has_elapsed_in_full_for_the_whole_cohort(self):
        creates(A, "COL001", madrid(date(2026, 9, 7)))
        joins(B, "COL001", madrid(date(2026, 9, 8)))  # cohort of W37
        joins(C, "COL001", madrid(date(2026, 9, 9)))
        creates(B, "COL00B", madrid(date(2026, 9, 12)))  # inside one week

        early = cohorts_as_of(week_bounds(W38)[1])  # the cutoff is the end of W38
        later = cohorts_as_of(week_bounds(date(2026, 10, 12))[1])

        assert early["2026-09-07"] == {"size": 2, "owners": 1, "owner_within": {"1": 1}}
        # 8 weeks after the cohort closed would be 9 Nov: still ahead of that cutoff.
        assert later["2026-09-07"] == {
            "size": 2,
            "owners": 1,
            "owner_within": {"1": 1, "2": 1, "4": 1},
        }

    def test_a_four_week_window_is_absent_when_it_has_not_gone_by(self):
        creates(A, "COL001", madrid(date(2026, 9, 7)))
        joins(B, "COL001", madrid(date(2026, 9, 8)))

        got = cohorts_as_of(week_bounds(W39)[1])

        assert "4" not in got["2026-09-07"]["owner_within"]
        assert "1" in got["2026-09-07"]["owner_within"]

    def test_every_snapshot_carries_the_triangle_outside_the_catalogue(self):
        creates(A, "COL001", madrid(date(2026, 9, 7)))
        joins(B, "COL001", madrid(date(2026, 9, 8)))

        got = week(W37)

        assert got["cohorts"]["2026-09-07"]["size"] == 1


@pytest.mark.django_db
class TestTheCatalogue:
    def test_a_snapshot_has_exactly_the_keys_of_the_catalogue_and_the_cohorts(self):
        got = week(W37)

        assert set(got) - {"cohorts"} == set(METRIC_KEYS)
        assert list(got)[:-1] == list(METRIC_KEYS)

    def test_a_rebuilt_week_has_no_value_for_what_only_the_present_can_say(self):
        got = week(W37)

        assert all(got[key] is None for key in LIVE_ONLY_KEYS)

    def test_a_live_week_fills_in_the_state_of_today_over_what_is_real(self, onboarding):
        owner = User.objects.create(code=A, email="lele@your-domain.test")
        Collection.objects.create(
            code="COL001",
            owner=owner,
            headline="Real",
            mode=Collection.Mode.COMMUNITY,
            visibility=Collection.Visibility.PUBLIC,
        )
        Collection.objects.create(code="COL002", owner=owner, headline="Private")
        Collection.objects.create(
            code="COL003", owner=owner, headline="Network", mode=Collection.Mode.NETWORK
        )

        got = week(W37, live=True)

        assert got["collections_community"] == 1
        assert got["collections_network"] == 1
        assert got["collections_public"] == 1
        assert got["things_available"] == 0


@pytest.mark.django_db
class TestWhatTheCharactersTouchStandsForNothing:
    """Rule 0: whoever acts, a character's collection or thing moves no number."""

    def test_a_person_joining_a_collection_of_a_character_moves_nothing(self):
        # Not an onboarding collection, and `seed_demo` leaves no events for it: only
        # the character's ownership says whose it is.
        Collection.objects.create(code="LALAC9", owner=person(LALA), headline="Lala's")
        joins(B, "LALAC9", madrid(date(2026, 9, 8)))

        got = week(W37)

        assert (got["new_people"], got["new_guests"], got["memberships"]) == (0, 0, 0)

    def test_a_request_on_a_thing_of_a_character_moves_nothing(self):
        Thing.objects.create(code="LALAT9", owner=person(LALA), headline="Lala's thing")
        asks(B, "LALAT9", madrid(date(2026, 9, 8)))

        assert week(W37)["requests"] == 0

    def test_the_fixed_codes_of_the_seed_count_even_when_nothing_of_them_exists(self):
        fixed = sorted(SEED_COLLECTION_CODES)[0]
        thing = sorted(SEED_THING_CODES)[0]
        joins(B, fixed, madrid(date(2026, 9, 8)))
        asks(C, thing, madrid(date(2026, 9, 8)))

        got = week(W37)

        assert (got["new_people"], got["requests"]) == (0, 0)

    def test_what_a_character_created_from_the_app_is_theirs_without_a_row_for_it(self):
        creates(LALA, "LALAC8", madrid(date(2026, 9, 8)), row=False)
        adds(LALA, "LALAT8", "LALAC8", madrid(date(2026, 9, 8)), row=False)
        joins(B, "LALAC8", madrid(date(2026, 9, 9)), row=False)
        asks(C, "LALAT8", madrid(date(2026, 9, 9)))

        got = week(W37)

        assert (got["collections"], got["things"], got["new_people"], got["requests"]) == (
            0,
            0,
            0,
            0,
        )

    def test_the_person_is_not_erased_only_that_event_stops_counting(self):
        Collection.objects.create(code="LALAC9", owner=person(LALA), headline="Lala's")
        creates(A, "COL001", madrid(date(2026, 9, 8)))
        joins(B, "LALAC9", madrid(date(2026, 9, 8)))  # their first join was in Lala's
        joins(B, "COL001", madrid(date(2026, 9, 15)))  # so this is the first real one

        history = _History(week_bounds(W39)[1])

        assert history.first_join[B].collection_code == "COL001"
        assert week(W37)["new_people"] == 1  # only A
        assert week(W38)["new_guests"] == 1  # B enters the cycle a week later


@pytest.mark.django_db
class TestAPhantomCollection:
    """Rule 1: created, never deleted, and gone from the database."""

    def test_it_and_everything_in_it_never_happened(self):
        creates(A, "GHOST1", madrid(date(2026, 9, 8)), row=False)
        adds(A, "GHOSTT", "GHOST1", madrid(date(2026, 9, 8)), row=False)
        joins(B, "GHOST1", madrid(date(2026, 9, 9)), row=False)
        asks(C, "GHOSTT", madrid(date(2026, 9, 9)))

        got = week(W37)

        for key in ("collections", "things", "memberships", "new_people", "requests"):
            assert got[key] == 0, key
        assert got["collections_created"] == 0

    def test_a_collection_that_exists_or_was_deleted_properly_is_not_one(self):
        creates(A, "LIVE01", madrid(date(2026, 9, 8)))
        creates(A, "GONE01", madrid(date(2026, 9, 8)), row=False)
        log(K.COLLECTION_DELETED, A, madrid(date(2026, 9, 10)), collection="GONE01")

        got = week(W37)

        assert got["collections_created"] == 2
        assert got["collections_deleted"] == 1
        assert got["collections"] == 1


@pytest.mark.django_db
class TestAnOrphanThingWithoutATrace:
    """Rule 2: its collection was deleted, it left no removal and it is not in the database."""

    def _story(self):
        creates(A, "DEL001", madrid(date(2026, 9, 8)), row=False)
        adds(A, "ORPH01", "DEL001", madrid(date(2026, 9, 8)), row=False)
        log(K.COLLECTION_DELETED, A, madrid(date(2026, 9, 17)), collection="DEL001")

    def test_it_counts_as_removed_from_the_week_its_collection_went(self):
        self._story()

        assert week(W37)["things"] == 1  # alive until the deletion
        assert week(W38)["things"] == 0  # the deletion of Thursday, week 38

    def test_it_is_not_a_movement_of_removed_things_that_week(self):
        self._story()

        assert week(W38)["things_removed"] == 0

    def test_a_thing_still_in_the_database_is_not_taken_for_one(self):
        creates(A, "DEL001", madrid(date(2026, 9, 8)), row=False)
        adds(A, "KEPT01", "DEL001", madrid(date(2026, 9, 8)))  # has its row
        log(K.COLLECTION_DELETED, A, madrid(date(2026, 9, 17)), collection="DEL001")

        assert week(W38)["things"] == 1


@pytest.mark.django_db
class TestAThingWithoutATraceInALiveCollection:
    """Rule 3: no row, no removal, and its collection exists: it never was."""

    def test_it_is_left_out_whole(self):
        creates(A, "COL001", madrid(date(2026, 9, 8)))
        adds(A, "REAL01", "COL001", madrid(date(2026, 9, 8)))
        adds(A, "GHOST2", "COL001", madrid(date(2026, 9, 8)), row=False)
        asks(B, "GHOST2", madrid(date(2026, 9, 9)))

        got = week(W37)

        assert (got["things"], got["things_added"], got["requests"]) == (1, 1, 0)

    def test_a_thing_removed_with_its_event_is_not_one(self):
        creates(A, "COL001", madrid(date(2026, 9, 8)))
        adds(A, "OLD001", "COL001", madrid(date(2026, 9, 8)), row=False)
        log(K.THING_REMOVED, A, madrid(date(2026, 9, 9)), thing="OLD001")

        got = week(W37)

        assert (got["things"], got["things_added"], got["things_removed"]) == (0, 1, 1)


@pytest.mark.django_db
class TestAPersonWhoNoLongerExists:
    """Rule 4: no row in `User` and memberships still open."""

    def test_their_memberships_close_at_their_last_event(self):
        creates(A, "COL001", madrid(date(2026, 9, 8)))
        joins(B, "COL001", madrid(date(2026, 9, 9)), row=False)
        asks(B, "THING1", madrid(date(2026, 9, 17)))  # their last trace, in week 38

        assert week(W37)["memberships"] == 1  # still there that week
        assert week(W38)["memberships"] == 0  # gone by the end of this one
        assert week(W38)["guests"] == 0

    def test_they_stay_in_the_history(self):
        creates(A, "COL001", madrid(date(2026, 9, 8)))
        joins(B, "COL001", madrid(date(2026, 9, 9)), row=False)

        assert week(W38)["new_people"] == 0
        assert week(W37)["new_people"] == 2  # A and B were there
        assert week(W37)["cycle_entered"] == 1

    def test_somebody_who_exists_keeps_their_membership(self):
        creates(A, "COL001", madrid(date(2026, 9, 8)))
        joins(B, "COL001", madrid(date(2026, 9, 9)))

        assert week(W39)["memberships"] == 1


@pytest.mark.django_db
class TestWhatVanishedAllTogether:
    def test_a_history_with_every_kind_of_hole_adds_up_to_the_database(self):
        # Real and whole.
        creates(A, "COL001", madrid(date(2026, 9, 8)))
        adds(A, "THING1", "COL001", madrid(date(2026, 9, 8)))
        joins(B, "COL001", madrid(date(2026, 9, 9)))
        # A phantom collection, with a thing and a member.
        creates(A, "GHOST1", madrid(date(2026, 9, 8)), row=False)
        adds(A, "GHOSTT", "GHOST1", madrid(date(2026, 9, 8)), row=False)
        joins(C, "GHOST1", madrid(date(2026, 9, 9)), row=False)
        # A deleted collection whose thing left no trace.
        creates(A, "DEL001", madrid(date(2026, 9, 8)), row=False)
        adds(A, "ORPH01", "DEL001", madrid(date(2026, 9, 8)), row=False)
        log(K.COLLECTION_DELETED, A, madrid(date(2026, 9, 10)), collection="DEL001")
        # A thing without a trace in the live collection.
        adds(A, "GHOST2", "COL001", madrid(date(2026, 9, 8)), row=False)
        # A person who was deleted.
        joins(D, "COL001", madrid(date(2026, 9, 9)), row=False)

        got = week(W37)

        assert got["collections"] == Collection.objects.count() == 1
        assert got["things"] == Thing.objects.count() == 1
        # B alive, D gone: the memberships of today are B's.
        assert got["memberships"] == 1
        assert got["guests"] == 1

    def test_the_holes_are_read_once_per_history_not_once_per_event(
        self, django_assert_num_queries
    ):
        creates(A, "COL001", madrid(date(2026, 9, 8)))
        for n in range(10):
            adds(A, f"TH{n:04d}", "COL001", madrid(date(2026, 9, 8)))
            joins(f"JN{n:04d}", "COL001", madrid(date(2026, 9, 9)))

        # The onboarding codes, the events, the two owner reads of the characters,
        # today's collections, things and users, the deletion markers and the last
        # event of each actor: nine however many events there are.
        with django_assert_num_queries(9):
            _History(week_bounds(W37)[1])

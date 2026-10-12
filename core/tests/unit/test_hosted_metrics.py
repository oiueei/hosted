"""One week of the series, derived from fabricated events (`hosted/metrics.py`).

**Tests code that is not in the standalone** (see `test_hosted_popin.py` for why the
file sits here).

Every event carries an explicit `created`, in Madrid time, so each test reads as a small
story: who did what on which day. Pinned: where a week begins and ends (across both
clock changes), what is excluded as demo, that people stay in the history after leaving,
the stocks, the stages of the cycle and their order, generations through a deleted
collection, requests apart from reservations, the medians and the shape of the catalogue.
"""

from datetime import UTC, date, datetime, timedelta

import pytest

from core.models import Collection, DailyActivity, Event, User
from hosted.metrics import (
    LIVE_ONLY_KEYS,
    METRIC_KEYS,
    WEEK_TZ,
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


def madrid(day, hour=12, minute=0):
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=WEEK_TZ)


def log(kind, who="", on=None, collection="", thing="", type="", source=""):
    return Event.objects.create(
        kind=kind,
        actor_code=who,
        collection_code=collection,
        thing_code=thing,
        thing_type=type,
        source=source,
        created=on,
    )


def creates(who, collection, on):
    return log(K.COLLECTION_CREATED, who, on, collection=collection)


def joins(who, collection, on, source=Event.Source.INVITE):
    return log(K.MEMBER_JOINED, who, on, collection=collection, source=source)


def adds(who, thing, collection, on, type="GIFT_THING"):
    return log(K.THING_ADDED, who, on, collection=collection, thing=thing, type=type)


def asks(who, thing, on, type="GIFT_THING"):
    return log(K.HOLD_REQUESTED, who, on, thing=thing, type=type)


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
        for person in (B, C, D):
            joins(person, "COL001", madrid(date(2026, 9, 9)))
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
        user_b = User.objects.create(code=B, email="lele@your-domain.test")
        user_c = User.objects.create(code=C, email="lili@your-domain.test")
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
        for code, mail in ((A, "lala@your-domain.test"), (B, "lele@your-domain.test")):
            user = User.objects.create(code=code, email=mail)
            DailyActivity.objects.create(user=user, date=date(2026, 9, 10))
        stranger = User.objects.create(code=C, email="lili@your-domain.test")
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

        got = week(W37, live=True)

        assert got["collections_community"] == 1
        assert got["collections_public"] == 1
        assert got["things_available"] == 0

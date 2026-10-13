"""Tests for the stats_summary command: demo/real partition, metrics, Monday gate."""

from datetime import date, timedelta
from io import StringIO

import pytest
import time_machine
from django.core import mail
from django.core.management import call_command
from django.utils import timezone

from core.management.commands.seed_data import common as seed_common
from core.models import FAQ, BookingPeriod, Collection, DailyActivity, Event, Thing, User
from core.tests.unit.test_hosted_metrics import LALA, adds, creates, joins, log, person
from hosted.management.commands.stats_summary import _fraction, build_report
from hosted.metrics import METRIC_KEYS, cycle_as_of
from hosted.models import Milestone, WeeklySnapshot

MONDAY = date(2026, 4, 20)
TUESDAY = date(2026, 4, 21)


def _row(sections, title, label):
    section = next(s for s in sections if s["title"] == title)
    return dict(section["rows"])[label]


def _real_collection(owner, code="RCOL01", **kwargs):
    return Collection.objects.create(
        code=code, owner=owner, headline="Real", is_onboarding=False, **kwargs
    )


@pytest.mark.django_db
class TestDemoPartition:
    def test_seed_and_onboarding_excluded_from_real(self):
        call_command("seed_demo", verbosity=0)
        sections = build_report()
        # Every seeded user only owns/joins onboarding collections → all demo.
        #
        # The two demo-funnel counts are read off the seed's own declaration
        # rather than written out. What this test is for is the partition — that
        # nothing seeded leaks into the real metrics — and hard numbers made it
        # fail for the one reason that is not a regression: the demo growing. It
        # broke the day a fourth and fifth onboarding collection were added here,
        # after the change had gone green upstream.
        assert _row(sections, "Users (real)", "Total real users") == 0
        assert _row(
            sections, "Demo funnel (NOT real metrics)", "Seed + onboarding-only users"
        ) == len(seed_common.USERS)
        assert _row(sections, "Demo funnel (NOT real metrics)", "Onboarding collections") == sum(
            1 for collection in seed_common.COLLECTIONS if collection.get("is_onboarding")
        )

    def test_onboarding_only_popin_user_is_demo(self, user):
        onboarding = Collection.objects.create(
            code="ONB001", owner=user, headline="W", is_onboarding=True
        )
        popin = User.objects.create(code="POPIN1", email="lala@your-domain.test")
        onboarding.invites.add(popin)
        sections = build_report()
        # user owns only an onboarding collection, popin only joined one → both demo.
        assert _row(sections, "Users (real)", "Total real users") == 0


@pytest.mark.django_db
class TestRealMetrics:
    def test_user_roles(self, user, user2):
        coll = _real_collection(user)
        coll.invites.add(user2)
        sections = build_report()
        assert _row(sections, "Users (real)", "Total real users") == 2
        assert _row(sections, "Users (real)", "Creators (own ≥1 real collection)") == 1
        assert _row(sections, "Users (real)", "Guests (invited only)") == 1

    def test_collection_mode_and_visibility(self, user):
        _real_collection(user, code="RC1", mode="COMMUNITY", visibility="PUBLIC")
        _real_collection(user, code="RC2", mode="PROPRIETARY", visibility="PRIVATE")
        sections = build_report()
        assert _row(sections, "Collections (real)", "Total") == 2
        assert _row(sections, "Collections (real)", "COMMUNITY / PROPRIETARY") == "1 / 1"
        assert _row(sections, "Collections (real)", "PUBLIC / PRIVATE") == "1 / 1"

    def test_things_by_type_and_proportions(self, user):
        coll = _real_collection(user)
        for i, ttype in enumerate(["GIFT_THING", "GIFT_THING", "SELL_THING", "LEND_THING"]):
            t = Thing.objects.create(code=f"RT{i:04d}", owner=user, headline="T", type=ttype)
            coll.things.add(t)
        sections = build_report()
        assert _row(sections, "Things (real)", "Total") == 4
        assert _row(sections, "Things (real)", "GIFT_THING") == "2 (50%)"
        assert _row(sections, "Things (real)", "SELL_THING") == "1 (25%)"

    def test_guests_who_never_booked(self, user, user2):
        coll = _real_collection(user)
        coll.invites.add(user2)  # a guest with no booking
        sections = build_report()
        assert (
            _row(sections, "Holds (real, current bookings)", "Guests who never booked")
            == "1 (100%)"
        )

    def test_hold_success_rate_and_faqs(self, user, user2):
        coll = _real_collection(user)
        coll.invites.add(user2)
        thing = Thing.objects.create(code="RTHS01", owner=user, headline="T", type="GIFT_THING")
        coll.things.add(thing)
        FAQ.objects.create(code="RFAQ01", thing=thing, questioner=user2, question="?")
        BookingPeriod.objects.create(
            code="RBK001",
            thing_code=thing,
            thing_type="GIFT_THING",
            requester_code=user2,
            requester_email=user2.email,
            owner_code=user,
            status="ACCEPTED",
        )
        BookingPeriod.objects.create(
            code="RBK002",
            thing_code=thing,
            thing_type="GIFT_THING",
            requester_code=user2,
            requester_email=user2.email,
            owner_code=user,
            status="PENDING",
        )
        sections = build_report()
        assert _row(sections, "Things (real)", "Avg FAQs per thing") == "1.0"
        assert _row(sections, "Holds (real, current bookings)", "Total hold requests") == 2
        assert (
            _row(sections, "Holds (real, current bookings)", "Success rate (accepted / requested)")
            == "50%"
        )


@pytest.mark.django_db
class TestEventAndRetentionMetrics:
    def test_history_counts_exclude_demo(self, user, user2):
        _real_collection(user).invites.add(user2)  # user + user2 are real
        onboarding = Collection.objects.create(
            code="ONB009", owner=user, headline="W", is_onboarding=True
        )
        demo_user = User.objects.create(code="DEMOXX", email="lele@your-domain.test")
        onboarding.invites.add(demo_user)  # only in an onboarding collection → demo

        Event.log(Event.Kind.USER_JOINED, actor=user)  # real → counts
        Event.log(Event.Kind.USER_JOINED, actor=demo_user)  # demo → excluded

        sections = build_report()
        joined = _row(
            sections, "History (accumulated, from Event log)", "Users joined (7d / 30d / all)"
        )
        assert joined == "1 / 1 / 1"

    def test_what_happens_in_a_characters_collection_is_not_counted_whoever_does_it(self, user):
        _real_collection(user)  # so that they are a real person
        lala = User.objects.create(code="La1aN1", email="lala@your-domain.test")
        Collection.objects.create(code="LALAC9", owner=lala, headline="Lala's")
        Thing.objects.create(code="LALAT9", owner=lala, headline="Lala's thing")
        Event.log(Event.Kind.MEMBER_JOINED, actor=user, collection="LALAC9")
        Event.log(Event.Kind.HOLD_REQUESTED, actor=user, thing="LALAT9")
        Event.log(Event.Kind.USER_JOINED, actor=user)  # about nothing of theirs: counts

        sections = build_report()
        title = "History (accumulated, from Event log)"

        assert _row(sections, title, "Members joined / left") == "0 / 0"
        assert _row(sections, title, "Holds requested / accepted") == "0 / 0"
        assert _row(sections, title, "Users joined (7d / 30d / all)") == "1 / 1 / 1"

    def test_things_added_removed_global_and_per_collection(self, user):
        # user owns 2 real collections → n_collections = 2 for the per-collection avg.
        _real_collection(user, code="HC1")
        _real_collection(user, code="HC2")
        for _ in range(3):
            Event.log(Event.Kind.THING_ADDED, actor=user)
        Event.log(Event.Kind.THING_REMOVED, actor=user)
        sections = build_report()
        title = "History (accumulated, from Event log)"
        assert _row(sections, title, "Things added / removed") == "3 / 1"
        # 3/2 added, 1/2 removed, one decimal (matches _avg formatting).
        assert _row(sections, title, "Avg added / removed per collection") == "1.5 / 0.5"

    def test_guest_to_creator_conversion(self, user, user2):
        # user2 joins a real collection as guest, then later creates their own.
        host = _real_collection(user, code="HOST01")
        host.invites.add(user2)
        own = _real_collection(user2, code="OWN001")
        now = timezone.now()
        Event.log(
            Event.Kind.MEMBER_JOINED, actor=user2, collection=host, created=now - timedelta(days=3)
        )
        Event.log(
            Event.Kind.COLLECTION_CREATED,
            actor=user2,
            collection=own,
            created=now - timedelta(days=1),
        )
        sections = build_report()
        assert _row(sections, "Conversion", "Guest → creator conversions") == 1

    def test_retention_wau_mau_and_return(self, user, user2):
        _real_collection(user).invites.add(user2)
        today = date.today()
        # user active two days (returner); user2 active once (never came back).
        DailyActivity.objects.create(code="DA0001", user=user, date=today)
        DailyActivity.objects.create(code="DA0002", user=user, date=today - timedelta(days=2))
        DailyActivity.objects.create(code="DA0003", user=user2, date=today)
        sections = build_report()
        # user (creator) active 2 days → a creator return; user2 (guest) active once.
        assert (
            _row(sections, "Retention (from DailyActivity)", "Creator returns (active ≥2 days)")
            == "1 returned (avg 2.0 active days)"
        )
        assert (
            _row(sections, "Retention (from DailyActivity)", "Guest returns (active ≥2 days)")
            == "0 returned (avg — active days)"
        )
        assert (
            _row(
                sections,
                "Retention (from DailyActivity)",
                "Guests who never came back after 1st visit",
            )
            == 1
        )


@pytest.mark.django_db
class TestStatsCommand:
    def test_stdout_always_printed(self):
        with time_machine.travel(TUESDAY):
            out = StringIO()
            call_command("stats_summary", stdout=out)
        text = out.getvalue()
        assert "OIUEEI stats summary" in text
        assert "email skipped" in text
        assert len(mail.outbox) == 0

    def test_monday_sends_email(self, monkeypatch):
        monkeypatch.setenv("STATS_EMAIL", "lala1@your-domain.test")
        with time_machine.travel(MONDAY):
            out = StringIO()
            call_command("stats_summary", stdout=out)
        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == ["lala1@your-domain.test"]
        assert "Stats email sent" in out.getvalue()

    def test_weekday_config_var_moves_the_email_day(self, monkeypatch):
        """STATS_EMAIL_WEEKDAY relocates the weekly send (here 1 = Tuesday)."""
        monkeypatch.setenv("STATS_EMAIL", "lala1@your-domain.test")
        monkeypatch.setenv("STATS_EMAIL_WEEKDAY", "1")
        with time_machine.travel(TUESDAY):
            out = StringIO()
            call_command("stats_summary", stdout=out)
        assert len(mail.outbox) == 1
        with time_machine.travel(MONDAY):
            out = StringIO()
            call_command("stats_summary", stdout=out)
        # Monday no longer sends once the day is moved.
        assert len(mail.outbox) == 1

    def test_garbage_weekday_config_falls_back_to_monday(self, monkeypatch):
        monkeypatch.setenv("STATS_EMAIL", "lala1@your-domain.test")
        monkeypatch.setenv("STATS_EMAIL_WEEKDAY", "friday")
        with time_machine.travel(MONDAY):
            out = StringIO()
            call_command("stats_summary", stdout=out)
        assert len(mail.outbox) == 1

    def test_email_flag_forces_send_on_non_monday(self, monkeypatch):
        monkeypatch.setenv("STATS_EMAIL", "lala1@your-domain.test")
        with time_machine.travel(TUESDAY):
            out = StringIO()
            call_command("stats_summary", "--email", stdout=out)
        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == ["lala1@your-domain.test"]

    def test_monday_skips_email_when_stats_email_unset(self, monkeypatch):
        """Third-party deploys must not email metrics to the author by default."""
        monkeypatch.delenv("STATS_EMAIL", raising=False)
        with time_machine.travel(MONDAY):
            out = StringIO()
            call_command("stats_summary", "--email", stdout=out)
        assert len(mail.outbox) == 0
        assert "STATS_EMAIL not set" in out.getvalue()


@pytest.mark.django_db
class TestJoinsByDoorSection:
    """The report has to separate the six doors, or C1 stays unanswerable.

    Every acquisition path was counted as the same `MEMBER_JOINED`, so "is this
    door earning its place?" had no answer in the data. The section exists to
    give that question one.
    """

    def _joined(self, source, actor, when=None):
        Event.objects.create(
            kind=Event.Kind.MEMBER_JOINED,
            actor_code=actor,
            collection_code="REALC1",
            source=source,
            created=when or timezone.now(),
        )

    def _section(self):
        return next(s for s in build_report() if s["title"] == "Members joined, by door")

    def test_each_door_is_counted_separately(self):
        self._joined(Event.Source.SHARE, "AAA111")
        self._joined(Event.Source.SHARE, "AAA222")
        self._joined(Event.Source.RECOMMENDATION, "AAA333")

        rows = dict(self._section()["rows"])

        assert rows["Share link / QR"].startswith("2 ")
        assert rows["Member recommendation"].startswith("1 ")
        assert rows["Owner invite"].startswith("0 ")

    def test_the_30_day_window_is_reported_beside_the_all_time_count(self):
        self._joined(Event.Source.PUBLIC, "AAA444")
        self._joined(Event.Source.PUBLIC, "AAA555", when=timezone.now() - timedelta(days=90))

        rows = dict(self._section()["rows"])

        # Two all time, one of them recent — an old door that has since gone
        # quiet must not read as a live one.
        assert rows["Public collection (login to act)"] == "2 (1 in 30d)"

    def test_joins_recorded_before_the_field_existed_get_their_own_bucket(self):
        """Never folded into a door they might not belong to."""
        self._joined("", "AAA666")

        rows = dict(self._section()["rows"])

        assert rows["Unrecorded (joined before this was measured)"] == 1

    def test_no_unrecorded_row_when_there_is_nothing_to_confess(self):
        self._joined(Event.Source.INVITE, "AAA777")

        labels = [label for label, _ in self._section()["rows"]]

        assert not any("Unrecorded" in label for label in labels)


# --- The weekly series in the Monday email ----------------------------------------


EVOLUTION = "Weekly evolution (last 12 weeks)"
CYCLE = "Organic cycle: guest → owner"
PHASES = "By phase"


def _snapshot(week_start, **values):
    metrics = dict.fromkeys(METRIC_KEYS, 0)
    metrics.update(values)
    metrics["cohorts"] = values.pop("cohorts", {})
    return WeeklySnapshot.objects.create(
        week_start=week_start,
        metrics=metrics,
        schema_version=1,
        origin=WeeklySnapshot.Origin.BACKFILL,
    )


def _titles(sections):
    return [s["title"] for s in sections]


def _section(sections, title):
    return next(s for s in sections if s["title"] == title)


@pytest.mark.django_db
class TestTheEvolutionSection:
    def test_each_week_shows_what_changed_since_the_one_before(self):
        _snapshot(date(2026, 10, 5), creators=6, guests=19, things=55, collections=8)
        _snapshot(
            date(2026, 10, 12),
            creators=7,
            guests=19,
            things=61,
            collections=9,
            requests=5,
            requests_accepted=3,
            reservations=2,
        )

        rows = _section(build_report(), EVOLUTION)["rows"]

        assert rows[0] == (
            "W42 · 12 Oct",
            "creators 7 (+1) · guests 19 (±0) · collections 9 · things 61 (+6) · "
            "requests 5 (3 ok) · reservations 2",
        )
        # The oldest has nothing before it to be compared with.
        assert rows[1][0] == "W41 · 5 Oct"
        assert rows[1][1].startswith("creators 6 · guests 19 · collections 8 · things 55 ·")

    def test_the_week_of_a_milestone_says_so(self):
        _snapshot(date(2026, 9, 7))
        Milestone.objects.create(
            date=date(2026, 9, 9), phase=Milestone.Phase.EARLY_ADOPTERS, label="Early adopters"
        )

        rows = _section(build_report(), EVOLUTION)["rows"]

        assert rows[0][0] == "W37 · 7 Sep ◆ Early adopters"

    def test_with_nothing_recorded_it_says_how_to_start(self):
        sections = build_report()

        row = _section(sections, EVOLUTION)["rows"][0]
        assert row[0] == "No weeks recorded yet"
        assert "record_weekly_snapshot --backfill-from 2026-09-07" in row[1]
        assert _section(sections, PHASES)["rows"][0][0] == "No weeks recorded yet"

    def test_only_the_last_twelve_weeks_are_listed(self):
        for n in range(14):
            _snapshot(date(2026, 9, 7) + timedelta(weeks=n))

        assert len(_section(build_report(), EVOLUTION)["rows"]) == 12


@pytest.mark.django_db
class TestTheCycleSection:
    def test_it_reports_the_funnel_the_generations_and_the_validation_beside_it(self):
        K = Event.Kind
        on = timezone.now() - timedelta(days=3)
        # The log tells a story whose collections still exist: what the log lost
        # without a trace is left out of the series.
        owner_a = User.objects.create(code="AAAAAA", email="oa@your-domain.test")
        owner_b = User.objects.create(code="BBBBBB", email="ob@your-domain.test")
        Collection.objects.create(code="COL001", owner=owner_a, headline="One")
        Collection.objects.create(code="COL002", owner=owner_b, headline="Two")
        Event.objects.create(
            kind=K.COLLECTION_CREATED, actor_code="AAAAAA", collection_code="COL001", created=on
        )
        Event.objects.create(
            kind=K.MEMBER_JOINED,
            actor_code="BBBBBB",
            collection_code="COL001",
            source="INVITE",
            created=on + timedelta(hours=1),
        )
        Event.objects.create(
            kind=K.COLLECTION_CREATED,
            actor_code="BBBBBB",
            collection_code="COL002",
            created=on + timedelta(days=1),
        )

        section = _section(build_report(), CYCLE)
        rows = dict(section["rows"])

        assert rows["Entered as a guest"] == 1
        assert rows["  became an owner"] == "1/1"
        assert rows["  came back (a second day)"] == "0/1"
        assert rows["Median guest → owner"] == "0.96 days"
        assert rows["Median owner → first request received"] == "—"
        assert rows["Creator validation (asked / approved)"] == "0 / 0"
        assert rows["K, generation 0 → 1"].startswith("1/1 = 1.00 · 1.0 guests brought per owner")
        assert "K above 1" in section["note"]
        assert any(label.endswith("(n=1)") for label, _ in section["rows"])

    def test_a_percentage_appears_only_when_the_sample_can_bear_it(self):
        assert _fraction(3, 9) == "3/9"
        assert _fraction(3, 10) == "3/10 (30%)"
        assert _fraction(0, 0) == "0/0"


@pytest.mark.django_db
class TestThePhasesSection:
    def test_each_phase_with_weeks_is_averaged_and_one_without_weeks_is_absent(self):
        Milestone.objects.create(
            date=date(2026, 9, 7), phase=Milestone.Phase.EARLY_ADOPTERS, label="x"
        )
        Milestone.objects.create(
            date=date(2026, 12, 1), phase=Milestone.Phase.DEV_LAUNCH, label="y"
        )
        _snapshot(date(2026, 9, 7), new_creators=2, new_guests=4, requests=1)
        _snapshot(
            date(2026, 9, 14),
            new_creators=1,
            new_guests=0,
            requests=2,
            cohorts={"2026-09-07": {"size": 4, "owners": 1, "owner_within": {}}},
        )

        rows = _section(build_report(), PHASES)["rows"]

        assert len(rows) == 1
        label, value = rows[0]
        assert label == "Early adopters (2 weeks)"
        assert "new creators 1.5" in value and "new guests 2.0" in value
        assert "requests 1.5" in value
        assert value.endswith("guest → owner 1/4")


@pytest.mark.django_db
class TestTheEmail:
    def test_it_carries_the_three_sections_with_a_milestone_label_escaped(self, monkeypatch):
        _snapshot(date(2026, 9, 7))
        Milestone.objects.create(
            date=date(2026, 9, 8), phase=Milestone.Phase.EARLY_ADOPTERS, label="<b>Early</b>"
        )
        monkeypatch.setenv("STATS_EMAIL", "lala@your-domain.test")

        call_command("stats_summary", "--email", stdout=StringIO())

        message = mail.outbox[0]
        html = message.alternatives[0][0]
        for title in (EVOLUTION, CYCLE, PHASES):
            assert title in message.body and title in html
        assert "&lt;b&gt;Early&lt;/b&gt;" in html
        assert "<b>Early</b>" not in html

    def test_the_new_sections_come_before_the_demo_funnel(self):
        titles = _titles(build_report())

        assert titles.index(EVOLUTION) < titles.index(CYCLE) < titles.index(PHASES)
        assert titles.index(PHASES) < titles.index("Demo funnel (NOT real metrics)")


@pytest.mark.django_db
class TestTheMondayEmailReadsWhatTheSeriesReads:
    """History, Conversion and Members joined, by door count from the series' events.

    The story: a real collection with a thing, a guest and a second guest; a phantom
    collection (created, never deleted, gone); a collection deleted with a thing that
    left no removal; and a character's collection that real people walked into.
    """

    HISTORY = "History (accumulated, from Event log)"
    DOORS = "Members joined, by door"

    @pytest.fixture
    def story(self):
        on = timezone.now() - timedelta(days=5)
        K = Event.Kind
        creates("OWNERA", "COL001", on)
        adds("OWNERA", "THING1", "COL001", on)
        for guest in ("GUESTB", "GUESTC"):
            Collection.objects.get(code="COL001").invites.add(person(guest))
        joins("GUESTB", "COL001", on + timedelta(hours=1), source=Event.Source.PUBLIC)
        joins("GUESTC", "COL001", on + timedelta(hours=1), source=Event.Source.INVITE)
        # Gone without a trace: a collection and its thing…
        creates("OWNERA", "GHOST1", on, row=False)
        adds("OWNERA", "GHOSTT", "GHOST1", on, row=False)
        joins("GUESTC", "GHOST1", on + timedelta(hours=2), source=Event.Source.SHARE, row=False)
        # …a collection deleted with a thing that left no removal…
        creates("OWNERA", "DEL001", on, row=False)
        adds("OWNERA", "ORPH01", "DEL001", on, row=False)
        log(K.COLLECTION_DELETED, "OWNERA", on + timedelta(hours=3), collection="DEL001")
        # …and a character's collection that a real person entered.
        Collection.objects.create(code="LALAC9", owner=person(LALA), headline="Lala's")
        joins("GUESTC", "LALAC9", on + timedelta(hours=4), source=Event.Source.SHARE)
        # GUESTB later starts a collection of their own; GUESTC only a phantom one.
        creates("GUESTB", "COLB01", on + timedelta(days=1))
        creates("GUESTC", "GHOST2", on + timedelta(days=1), row=False)

    def test_history_counts_neither_the_phantom_nor_the_characters_and_retires_the_orphan(
        self, story
    ):
        sections = build_report()

        # COL001, DEL001 and COLB01 were created, DEL001 deleted: the phantoms are out.
        assert _row(sections, self.HISTORY, "Collections created / deleted") == "3 / 1"
        # THING1 and ORPH01 were added; ORPH01 went with its collection.
        assert _row(sections, self.HISTORY, "Things added / removed") == "2 / 1"
        # The two real joins; the phantom's and the character's are out.
        assert _row(sections, self.HISTORY, "Members joined / left") == "2 / 0"

    def test_history_says_why_created_minus_deleted_can_differ_from_today(self, story):
        section = next(s for s in build_report() if s["title"] == self.HISTORY)

        assert "older than the log" in section["note"]

    def test_users_joined_still_leaves_out_the_visit_of_the_open_door(self, story):
        onboarding_owner = person("ONBOWN")
        Collection.objects.create(
            code="ONBCOL", owner=onboarding_owner, headline="Demo", is_onboarding=True
        )
        visitor = person("POPIN1")
        Collection.objects.get(code="ONBCOL").invites.add(visitor)
        log(Event.Kind.USER_JOINED, "POPIN1", timezone.now() - timedelta(days=1))
        log(Event.Kind.USER_JOINED, "GUESTB", timezone.now() - timedelta(days=1))

        sections = build_report()

        assert _row(sections, self.HISTORY, "Users joined (7d / 30d / all)") == "1 / 1 / 1"

    def test_conversions_are_the_owners_of_the_cycle(self, story):
        sections = build_report()
        conversions = _row(sections, "Conversion", "Guest → creator conversions")

        # Only GUESTB made a real collection after joining; GUESTC's was a phantom.
        assert conversions == 1
        assert conversions == cycle_as_of(timezone.now())["cycle_owner"]

    def test_the_doors_count_only_real_joins_in_their_own_door(self, story):
        sections = build_report()

        assert _row(sections, self.DOORS, "Public collection (login to act)") == "1 (1 in 30d)"
        assert _row(sections, self.DOORS, "Owner invite") == "1 (1 in 30d)"
        # The phantom's and the character's joins, both through a share link, are out.
        assert _row(sections, self.DOORS, "Share link / QR") == "0 (0 in 30d)"

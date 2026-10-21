"""``send_join_summaries``: each curator is told, once, who joined their group."""

import html
from datetime import datetime, time, timedelta
from io import StringIO

import pytest
import time_machine
from django.core import mail
from django.core.management import call_command
from django.utils import timezone

from core.models.collection import Collection
from core.models.event import Event
from core.models.user import User


def _noon(days_ago):
    day = timezone.localdate() - timedelta(days=days_ago)
    return timezone.make_aware(datetime.combine(day, time(12, 0)))


def run():
    out, err = StringIO(), StringIO()
    call_command("send_join_summaries", stdout=out, stderr=err)
    return out.getvalue(), err.getvalue()


@pytest.fixture
def group(db):
    owner = User.objects.create(code="JSO001", email="lala@your-domain.test", name="Lala")
    co = User.objects.create(code="JSO002", email="lele@your-domain.test", name="Lele")
    collection = Collection.objects.create(code="JSC001", owner=owner, headline="The street")
    collection.co_owners.add(co)
    collection.invites.add(co)
    collection.team = (owner, co)
    return collection


def join(collection, name, days_ago=1, stay=True, code=None):
    n = User.objects.count()
    person = User.objects.create(
        code=code or f"JSN{n:03d}", email=f"p{n}@your-domain.test", name=name
    )
    Event.log(
        Event.Kind.MEMBER_JOINED, actor=person, collection=collection, created=_noon(days_ago)
    )
    if stay:
        collection.invites.add(person)
    return person


def to(address):
    return [m for m in mail.outbox if m.to == [address]]


class TestWhoIsTold:
    def test_one_email_per_curator_with_yesterdays_names(self, group):
        join(group, "Lili")
        join(group, "Lolo")
        run()
        assert len(mail.outbox) == 2
        for address in ("lala@your-domain.test", "lele@your-domain.test"):
            (message,) = to(address)
            assert "Lili" in message.body and "Lolo" in message.body
            assert "2" in message.subject

    def test_nothing_without_sign_ups(self, group):
        out, _ = run()
        assert mail.outbox == []
        assert "Sent 0" in out

    def test_todays_sign_ups_wait_for_tomorrow(self, group):
        join(group, "Lili", days_ago=0)
        run()
        assert mail.outbox == []

    def test_a_curator_who_joined_is_not_told_about_themselves(self, group):
        Event.log(
            Event.Kind.MEMBER_JOINED,
            actor=group.co_owners.get(),
            collection=group,
            created=_noon(1),
        )
        join(group, "Lili")
        run()
        assert "Lili" in to("lele@your-domain.test")[0].body
        assert "Lele" in to("lala@your-domain.test")[0].body
        assert "Lele" not in to("lele@your-domain.test")[0].body

    def test_a_curator_who_is_the_only_one_to_join_gets_nothing(self, group):
        Event.log(
            Event.Kind.MEMBER_JOINED,
            actor=group.co_owners.get(),
            collection=group,
            created=_noon(1),
        )
        run()
        assert to("lele@your-domain.test") == []
        assert len(to("lala@your-domain.test")) == 1

    def test_only_active_collections(self, group):
        join(group, "Lili")
        Collection.objects.filter(pk=group.pk).update(status=Collection.Status.INACTIVE)
        run()
        assert mail.outbox == []

    def test_activity_off_gets_nothing(self, group):
        join(group, "Lili")
        User.objects.filter(email="lele@your-domain.test").update(notify_activity=False)
        run()
        assert to("lele@your-domain.test") == []
        assert len(to("lala@your-domain.test")) == 1

    def test_someone_who_left_is_not_named(self, group):
        join(group, "Lili")
        join(group, "Gone", stay=False)
        run()
        body = to("lala@your-domain.test")[0].body
        assert "Lili" in body and "Gone" not in body

    def test_everybody_gone_sends_nothing_but_still_claims_the_day(self, group):
        join(group, "Gone", stay=False)
        run()
        assert mail.outbox == []
        group.refresh_from_db()
        assert group.join_summary_sent_on == timezone.localdate() - timedelta(days=1)

    def test_a_nameless_member_is_named_to_the_team_by_their_address(self, group):
        person = join(group, "")
        join(group, "Lili")
        run()
        for curator in ("lala@your-domain.test", "lele@your-domain.test"):
            message = to(curator)[0]
            assert f"{person.email} and Lili" in message.body
            assert "a member" not in message.body
            assert person.email in html.unescape(message.alternatives[0][0])

    def test_a_named_member_does_not_bring_their_address_along(self, group):
        person = join(group, "Lili")
        run()
        message = to("lala@your-domain.test")[0]
        assert person.email not in message.body
        assert person.email not in html.unescape(message.alternatives[0][0])

    def test_a_nameless_address_is_escaped_in_the_html(self, group):
        join(group, "")
        User.objects.filter(email="p2@your-domain.test").update(email="a&b<x>@your-domain.test")
        run()
        page = to("lala@your-domain.test")[0].alternatives[0][0]
        assert "a&amp;b&lt;x&gt;@your-domain.test" in page and "<x>" not in page

    def test_the_plain_text_names_the_group_once_at_the_top(self, group):
        join(group, "Lili")
        run()
        body = to("lala@your-domain.test")[0].body
        # `_send` puts the header on the first line; the summary must not add a
        # second copy of it before its own intro.
        first, second = body.split("\n\n")[:2]
        assert first == "The street"
        assert second != "The street"

    def test_the_button_goes_to_the_members_page(self, group):
        join(group, "Lili")
        run()
        message = to("lala@your-domain.test")[0]
        assert f"{group.path()}/invites" in message.body
        assert f"{group.path()}/invites" in message.alternatives[0][0]


class TestNamesAndLanguages:
    def test_ten_names_then_and_n_more_from_eleven(self, group):
        for i in range(11):
            join(group, f"Guest{i:02d}")
        run()
        body = to("lala@your-domain.test")[0].body
        assert "Guest09" in body and "Guest10" not in body
        assert "Guest08, Guest09 and 1 more." in body
        assert "and and" not in body
        assert "11" in to("lala@your-domain.test")[0].subject

    def test_the_closing_more_replaces_the_conjunction_in_spanish(self, group):
        User.objects.filter(email="lala@your-domain.test").update(language="es")
        for i in range(12):
            join(group, f"Guest{i:02d}")
        run()
        body = to("lala@your-domain.test")[0].body
        assert "Guest09 y 2 más." in body
        assert "y y" not in body

    def test_ten_names_have_no_more(self, group):
        for i in range(10):
            join(group, f"Guest{i:02d}")
        run()
        body = to("lala@your-domain.test")[0].body
        assert "Guest09" in body and "more" not in body

    @pytest.mark.parametrize(
        "lang,subject,intro,more,cta",
        [
            (
                "en",
                "2 new people in The street",
                "New in The street: Lili and Lolo.",
                None,
                "See the members",
            ),
            (
                "es",
                "2 personas nuevas en The street",
                "Se han unido a The street: Lili y Lolo.",
                None,
                "Ver los miembros",
            ),
            (
                "ca",
                "2 persones noves a The street",
                "S'han unit a The street: Lili i Lolo.",
                None,
                "Veure els membres",
            ),
        ],
    )
    def test_each_language(self, group, lang, subject, intro, more, cta):
        User.objects.filter(email="lala@your-domain.test").update(language=lang)
        join(group, "Lili")
        join(group, "Lolo")
        run()
        message = to("lala@your-domain.test")[0]
        assert message.subject.endswith(subject)
        assert intro in message.body
        assert cta in html.unescape(message.alternatives[0][0])

    def test_one_person_reads_in_the_singular(self, group):
        User.objects.filter(email="lala@your-domain.test").update(language="es")
        join(group, "Lili")
        run()
        message = to("lala@your-domain.test")[0]
        assert "Una persona nueva" in message.subject
        assert "Se ha unido a The street: Lili." in message.body


class TestOncePerDay:
    def test_two_runs_the_same_day_send_one_email(self, group):
        join(group, "Lili")
        run()
        sent = len(mail.outbox)
        run()
        assert sent == 2 and len(mail.outbox) == 2

    def test_a_skipped_day_is_picked_up(self, group):
        Collection.objects.filter(pk=group.pk).update(
            join_summary_sent_on=timezone.localdate() - timedelta(days=4)
        )
        join(group, "Two", days_ago=2)
        join(group, "Three", days_ago=3)
        run()
        body = to("lala@your-domain.test")[0].body
        assert "Two" in body and "Three" in body

    def test_what_was_already_told_is_not_told_again(self, group):
        Collection.objects.filter(pk=group.pk).update(
            join_summary_sent_on=timezone.localdate() - timedelta(days=3)
        )
        join(group, "Old", days_ago=3)
        join(group, "Fresh", days_ago=1)
        run()
        body = to("lala@your-domain.test")[0].body
        assert "Fresh" in body and "Old" not in body

    def test_never_more_than_seven_days_back(self, group):
        join(group, "Ancient", days_ago=8)
        join(group, "Edge", days_ago=7)
        Collection.objects.filter(pk=group.pk).update(
            join_summary_sent_on=timezone.localdate() - timedelta(days=30)
        )
        run()
        body = to("lala@your-domain.test")[0].body
        assert "Edge" in body and "Ancient" not in body

    def test_a_first_run_names_only_yesterday(self, group):
        join(group, "Earlier", days_ago=3)
        join(group, "Fresh", days_ago=1)
        run()
        body = to("lala@your-domain.test")[0].body
        assert "Fresh" in body and "Earlier" not in body

    def test_a_pass_dates_the_groups_with_nothing_to_tell_and_leaves_older_dates_alone(self, group):
        older = timezone.localdate() - timedelta(days=5)
        other = Collection.objects.create(
            code="JSC002", owner=group.owner, headline="Other", join_summary_sent_on=older
        )
        run()
        yesterday = timezone.localdate() - timedelta(days=1)
        group.refresh_from_db()
        other.refresh_from_db()
        assert group.join_summary_sent_on == yesterday
        assert other.join_summary_sent_on == older

    def test_a_sign_up_on_a_day_the_scheduler_skipped_is_not_lost_in_a_quiet_group(self, group):
        """A group with no sign-ups for weeks has no date yet. If its first one
        lands on a skipped day, it must not be read as a "first summary" (which
        names only yesterday)."""
        assert group.join_summary_sent_on is None
        now = timezone.now()
        with time_machine.travel(now - timedelta(days=2), tick=False):
            run()  # nothing to tell; it still looks at the group
        join(group, "Late", days_ago=2)
        # The scheduler does not run the next day; two days after the sign-up it does.
        run()
        assert "Late" in to("lala@your-domain.test")[0].body

    def test_a_group_whose_sends_all_failed_is_still_to_be_told(self, group, monkeypatch):
        join(group, "Lili")

        def boom(*a, **k):
            raise RuntimeError("smtp down")

        monkeypatch.setattr(
            "core.management.commands.send_join_summaries.send_join_summary_email", boom
        )
        run()
        group.refresh_from_db()
        assert group.join_summary_sent_on is None, "handed back, not dated as looked at"

    def test_the_claim_is_taken_before_sending(self, group, monkeypatch):
        join(group, "Lili")
        seen = []

        def spy(collection, curator, names):
            seen.append(Collection.objects.get(pk=collection.pk).join_summary_sent_on)

        monkeypatch.setattr(
            "core.management.commands.send_join_summaries.send_join_summary_email", spy
        )
        run()
        assert seen and set(seen) == {timezone.localdate() - timedelta(days=1)}

    def test_a_lost_race_sends_nothing(self, group, monkeypatch):
        join(group, "Lili")
        yesterday = timezone.localdate() - timedelta(days=1)
        # Another run claims the day between this one's read and its claim.
        Collection.objects.filter(pk=group.pk).update(join_summary_sent_on=yesterday)
        from core.management.commands import send_join_summaries as cmd

        stale = Collection.objects.get(pk=group.pk)
        stale.join_summary_sent_on = None
        cmd.Command()._summarise(stale, yesterday, yesterday - timedelta(days=6))
        assert mail.outbox == []

    def test_a_failure_gives_the_claim_back(self, group, monkeypatch):
        join(group, "Lili")
        before = timezone.localdate() - timedelta(days=2)
        Collection.objects.filter(pk=group.pk).update(join_summary_sent_on=before)

        def boom(*a, **k):
            raise RuntimeError("smtp down")

        monkeypatch.setattr(
            "core.management.commands.send_join_summaries.send_join_summary_email", boom
        )
        _, err = run()
        assert "Join summary failed" in err
        group.refresh_from_db()
        assert group.join_summary_sent_on == before
        monkeypatch.undo()
        run()
        assert len(mail.outbox) == 2

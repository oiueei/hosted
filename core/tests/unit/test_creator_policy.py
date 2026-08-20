"""`CREATOR_POLICY` — the one place a deployment says who may create what.

Two behaviours are what these tests exist for, and the second is the subtle one:

1. **The standalone gate is not a gate.** `OpenCreatorPolicy` says yes to every
   mode and every verb, for everyone, always. If that ever stops being true,
   upstream OIUEEI has silently grown a restriction it does not want.
2. **Enforcement and the advertised capabilities are the same answer.** They are
   read by different layers — a 403 in a serializer, a JSON blob the SPA renders
   from — and a gate written twice is a gate that drifts. Here they are derived
   from one `capabilities()` call, and these tests hold them to it.
"""

import json

import pytest
from django.conf import settings
from django.test import override_settings

from core.models import Collection, Thing
from core.services import creator_policy
from core.services.creator_policy import (
    Capabilities,
    CreatorPolicy,
    OpenCreatorPolicy,
    collection_mode_denial,
    get_creator_policy,
    thing_type_denial,
)
from core.tests.sample_creator_policy import REQUEST_URL

RESTRICTED = "core.tests.sample_creator_policy.RestrictedCreatorPolicy"
SILENT = "core.tests.sample_creator_policy.SilentlyRestrictedCreatorPolicy"


@pytest.mark.django_db
class TestTheStandaloneIsUngated:
    """`OpenCreatorPolicy` is what an upstream checkout runs. It must refuse nothing."""

    @pytest.mark.parametrize("mode", Collection.Mode.values)
    def test_every_collection_mode_the_model_offers_is_allowed(self, user, mode):
        """Parametrised over the model's own choices, not a copy of them.

        A mode added to `Collection.Mode` and forgotten here would otherwise
        ship as quietly unavailable — the standalone offering less than the
        schema does.
        """
        assert OpenCreatorPolicy().allows_collection_mode(user, mode)
        assert collection_mode_denial(user, mode) is None

    @pytest.mark.parametrize("thing_type", Thing.Type.values)
    def test_every_thing_type_the_model_offers_is_allowed(self, user, thing_type):
        assert OpenCreatorPolicy().allows_thing_type(user, thing_type)
        assert thing_type_denial(user, thing_type) is None

    def test_there_is_nowhere_to_request_access_because_there_is_nothing_to_request(self, user):
        assert OpenCreatorPolicy().capabilities(user).request_url is None

    def test_the_answer_does_not_depend_on_who_is_asking(
        self, user, user2, django_assert_num_queries
    ):
        """No user is more equal — and upstream reaches nothing to find out.

        `user2` is genuinely deactivated (saved, not just set on the instance):
        a policy that had quietly started consulting something about the person
        would be free to answer differently for an account in that state, and
        the equality below is what would catch it.

        The query count is the same promise from the other side, and the half
        that cannot be satisfied vacuously. `capabilities_for` is deliberately
        uncached and `/auth/me/` calls it on every app load, so the standalone's
        answer has to come off the model choices and cost nothing. A subclass or
        a refactor that reached for the database here — the shape every policy
        this setting exists for has — would fail here rather than on the
        deployment paying for it.
        """
        user2.is_active = False
        user2.save(update_fields=["is_active"])

        with django_assert_num_queries(0):
            stranger = OpenCreatorPolicy().capabilities(user2)

            assert stranger == OpenCreatorPolicy().capabilities(user)

    def test_it_is_the_default_when_nothing_is_configured(self, user):
        """The setting's default — what a self-hoster gets without an .env entry."""
        assert isinstance(get_creator_policy(), OpenCreatorPolicy)
        assert settings.CREATOR_POLICY == "core.services.creator_policy.OpenCreatorPolicy"


@pytest.mark.django_db
class TestSwappingThePolicy:
    def test_the_setting_decides_which_class_runs(self, user):
        with override_settings(CREATOR_POLICY=RESTRICTED):
            assert get_creator_policy().allows_collection_mode(user, Collection.Mode.COMMUNITY) is (
                False
            )

    def test_the_instance_is_cached_per_path_but_the_setting_is_read_every_time(self, user):
        """The cache must sit under the lookup, not over it.

        Caching the *resolved policy* in a module global is the obvious way to
        avoid re-importing on every request, and it silently pins the first
        policy a process ever loaded — which in a test run means the first test
        file to touch it decides for all the others.
        """
        first = get_creator_policy()
        assert get_creator_policy() is first  # same path → same instance, not re-imported

        with override_settings(CREATOR_POLICY=RESTRICTED):
            assert get_creator_policy() is not first

        assert get_creator_policy() is first  # and back, once the override lifts


@pytest.mark.django_db
class TestARestrictedDeployment:
    def test_a_held_back_mode_is_refused_and_the_message_names_it(self, user):
        with override_settings(CREATOR_POLICY=RESTRICTED):
            denial = collection_mode_denial(user, Collection.Mode.COMMUNITY)

        assert denial is not None
        assert "COMMUNITY" in denial

    def test_what_the_policy_still_allows_is_not_refused(self, user):
        """A narrower policy narrows; it does not close the product."""
        with override_settings(CREATOR_POLICY=RESTRICTED):
            assert collection_mode_denial(user, Collection.Mode.PROPRIETARY) is None
            assert thing_type_denial(user, Thing.Type.GIFT_THING) is None

    @pytest.mark.parametrize("thing_type", [Thing.Type.LEND_THING, Thing.Type.RENT_THING])
    def test_a_held_back_verb_is_refused_in_words_a_person_reads(self, user, thing_type):
        with override_settings(CREATOR_POLICY=RESTRICTED):
            denial = thing_type_denial(user, thing_type)

        assert denial is not None
        # "lend thing", not "LEND_THING" — this text reaches an API client as
        # the 403 body, so it is prose rather than a constant.
        assert thing_type.replace("_", " ").lower() in denial
        assert thing_type not in denial

    def test_the_refusal_says_where_to_ask_when_there_is_somewhere(self, user):
        """The 403 has to carry it too, not just `GET /auth/me/`.

        A client using the API without the SPA sees only the refusal, and would
        otherwise never learn that asking is possible.
        """
        with override_settings(CREATOR_POLICY=RESTRICTED):
            assert REQUEST_URL in collection_mode_denial(user, Collection.Mode.COMMUNITY)
            assert REQUEST_URL in thing_type_denial(user, Thing.Type.LEND_THING)

    def test_a_deployment_with_nowhere_to_ask_does_not_invite_the_user_to_ask(self, user):
        with override_settings(CREATOR_POLICY=SILENT):
            denial = collection_mode_denial(user, Collection.Mode.COMMUNITY)

        assert "COMMUNITY" in denial
        assert "Request access" not in denial
        assert "None" not in denial  # the null URL must not be formatted into prose


@pytest.mark.django_db
class TestThePolicyContract:
    def test_allows_is_derived_from_capabilities_not_declared_beside_it(self, user):
        """A subclass overrides one method and the two `allows_*` follow.

        This is what keeps the 403 and the advertised capabilities in agreement:
        a policy that could answer "yes" to something it left out of its own
        capabilities would be a policy the UI misreports.
        """

        class OnlyCapabilities(CreatorPolicy):
            def capabilities(self, unused_user):
                return Capabilities(collection_modes=("PROPRIETARY",), thing_types=())

        policy = OnlyCapabilities()
        assert policy.allows_collection_mode(user, "PROPRIETARY")
        assert not policy.allows_collection_mode(user, "COMMUNITY")
        assert not policy.allows_thing_type(user, Thing.Type.GIFT_THING)

    def test_the_base_class_refuses_to_guess(self, user):
        with pytest.raises(NotImplementedError):
            CreatorPolicy().capabilities(user)

    def test_capabilities_serialise_to_json_as_lists(self, user):
        """`as_dict()` is the wire shape; tuples are not JSON."""
        payload = OpenCreatorPolicy().capabilities(user).as_dict()

        assert json.loads(json.dumps(payload)) == payload
        assert payload["collection_modes"] == list(Collection.Mode.values)
        assert payload["thing_types"] == list(Thing.Type.values)
        assert payload["request_url"] is None


class CountingPolicy(CreatorPolicy):
    """Records how often it is consulted. Everything is withheld, so every ask
    takes the denial path — the expensive one, and the one that used to ask twice."""

    def __init__(self):
        self.calls = 0

    def capabilities(self, user):
        self.calls += 1
        return Capabilities(
            collection_modes=(),
            thing_types=(),
            request_url="https://example.org/request-access/",
        )


@pytest.mark.django_db
class TestThePolicyIsConsultedOnce:
    """How *often* a policy is asked is part of its contract.

    `CreatorPolicy` requires subclasses to be stateless, not cheap — and the
    policies this setting exists for are the ones that go and look something up.
    Upstream the answer is two tuples off the model choices, so nothing here is
    visible in the standalone; on the deployment that narrows, it is the
    difference between one query and a hundred.
    """

    @pytest.fixture
    def policy(self, monkeypatch):
        instance = CountingPolicy()
        monkeypatch.setattr(creator_policy, "get_creator_policy", lambda: instance)
        return instance

    def test_a_refusal_asks_once_though_it_needs_two_answers(self, policy, user):
        """The denial needs the list *and* the request URL. That is one question.

        It used to be two: `allows_collection_mode()` resolved the capabilities,
        then `_denial` resolved them again for the URL — so the refusal path
        cost double the allow path, on exactly the deployments that pay for it.
        """
        assert creator_policy.collection_mode_denial(user, Collection.Mode.COMMUNITY)

        assert policy.calls == 1

    def test_a_thing_refusal_likewise(self, policy, user):
        assert creator_policy.thing_type_denial(user, Thing.Type.LEND_THING)

        assert policy.calls == 1

    def test_a_caller_holding_the_answer_is_not_made_to_ask_again(self, policy, user):
        """What lets `ThingBulkCreateView` judge a hundred rows with one question.

        The verb is per row; whether this deployment offers it is not. Without
        the hoist, a CSV import ran one policy evaluation per line — and a
        policy backed by a table would have run one query per line.
        """
        capabilities = creator_policy.capabilities_for(user)
        assert policy.calls == 1

        for _ in range(100):
            assert creator_policy.thing_type_denial(
                user, Thing.Type.LEND_THING, capabilities=capabilities
            )

        assert policy.calls == 1


class PerUserPolicy(CreatorPolicy):
    """Answers differently depending on who is asking — the whole reason the
    setting takes a class instead of a list.

    Every other policy in this file, and both samples, ignore `user` and return
    a constant. That is honest for what they test, and it left the argument
    itself unguarded: nothing proved the person actually reaches the policy.
    """

    ALLOWED_EMAIL = "vetted@example.com"

    def capabilities(self, user):
        vetted = getattr(user, "email", None) == self.ALLOWED_EMAIL
        return Capabilities(
            collection_modes=tuple(Collection.Mode.values) if vetted else ("PROPRIETARY",),
            thing_types=tuple(Thing.Type.values) if vetted else (Thing.Type.GIFT_THING,),
            request_url="https://example.test/vetting/",
        )


PER_USER = "core.tests.unit.test_creator_policy.PerUserPolicy"


@pytest.mark.django_db
class TestThePolicyIsAskedAboutThePersonAsking:
    """`user` reaches the policy — at every door, not just the first.

    The deployments this setting exists for decide **per person**: a co-op whose
    board opens COMMUNITY collections, an operator who vets before lending is on
    offer. Every policy in the test suite answered a constant, so passing the
    wrong user — or none — was invisible: a scoped mutation run replaced `user`
    with `None` in `allows_collection_mode`, `allows_thing_type`,
    `capabilities_for` and both denial helpers, and **all five mutants lived**
    through a suite that has this module at 100% line coverage.

    On a real vetting policy that bug reads as "nobody is vetted" (or, worse,
    "everybody is"), for every account at once.
    """

    @pytest.fixture
    def vetted(self, user):
        user.email = PerUserPolicy.ALLOWED_EMAIL
        user.save(update_fields=["email"])
        return user

    def test_capabilities_for_answers_for_the_user_it_was_given(self, vetted, user2):
        with override_settings(CREATOR_POLICY=PER_USER):
            assert creator_policy.capabilities_for(vetted).collection_modes == tuple(
                Collection.Mode.values
            )
            assert creator_policy.capabilities_for(user2).collection_modes == ("PROPRIETARY",)

    def test_the_two_allows_helpers_carry_the_user_through(self, vetted, user2):
        with override_settings(CREATOR_POLICY=PER_USER):
            policy = get_creator_policy()

            assert policy.allows_collection_mode(vetted, Collection.Mode.COMMUNITY)
            assert not policy.allows_collection_mode(user2, Collection.Mode.COMMUNITY)
            assert policy.allows_thing_type(vetted, Thing.Type.LEND_THING)
            assert not policy.allows_thing_type(user2, Thing.Type.LEND_THING)

    def test_both_denials_judge_the_person_in_front_of_them(self, vetted, user2):
        """The refusal path too — it resolves the capabilities itself."""
        with override_settings(CREATOR_POLICY=PER_USER):
            assert collection_mode_denial(vetted, Collection.Mode.COMMUNITY) is None
            assert collection_mode_denial(user2, Collection.Mode.COMMUNITY) is not None

            assert thing_type_denial(vetted, Thing.Type.LEND_THING) is None
            assert thing_type_denial(user2, Thing.Type.LEND_THING) is not None

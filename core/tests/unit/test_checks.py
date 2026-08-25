"""The deploy-time check on `CREATOR_POLICY` (`core/checks.py`).

What it protects is not a feature but a *class of outage*: the setting resolves
lazily, so before this check a typo in a config var passed `manage.py check`,
passed the Heroku release phase, booted, and then 500'd `GET /auth/me/` — the
endpoint the SPA calls on every load. The deploy had already been declared
successful by then.

So each test below is one shape of "wrong" an operator can actually type, and
the assertion is always the same: it is an *error at check time*, not a
traceback at request time.
"""

import pytest
from django.core.checks import Error
from django.core.management import call_command
from django.core.management.base import SystemCheckError
from django.test import override_settings

from core.checks import check_creator_policy, check_object_storage
from core.services.creator_policy import Capabilities, CreatorPolicy


class PolicyNeedingArguments(CreatorPolicy):
    """Imports cleanly, cannot be constructed the way `get_creator_policy()` does."""

    def __init__(self, quota):
        self.quota = quota

    def capabilities(self, user) -> Capabilities:
        return Capabilities(collection_modes=(), thing_types=())


class NotAPolicy:
    """A perfectly importable class that is not one of ours."""


def ids(errors):
    return [error.id for error in errors]


@pytest.mark.django_db
class TestCreatorPolicyCheck:
    def test_the_shipped_default_passes(self):
        """The standalone must boot clean, or the check is worse than nothing."""
        assert check_creator_policy(None) == []

    def test_a_real_subclass_passes(self):
        with override_settings(
            CREATOR_POLICY="core.tests.sample_creator_policy.RestrictedCreatorPolicy"
        ):
            assert check_creator_policy(None) == []

    def test_a_mistyped_path_is_an_error_not_a_500_later(self):
        """The exact scenario: a config var with a typo in it."""
        with override_settings(CREATOR_POLICY="deployment.policy.Typo"):
            errors = check_creator_policy(None)

        assert ids(errors) == ["core.E002"]
        assert isinstance(errors[0], Error)
        # The message names the setting, because the operator reading a failed
        # deploy has only this line to work from.
        assert "CREATOR_POLICY" in errors[0].msg
        assert "deployment.policy.Typo" in errors[0].msg

    def test_a_real_module_with_a_wrong_attribute_is_caught(self):
        with override_settings(CREATOR_POLICY="core.services.creator_policy.NoSuchPolicy"):
            assert ids(check_creator_policy(None)) == ["core.E002"]

    def test_something_importable_that_is_not_a_policy_is_caught(self):
        with override_settings(CREATOR_POLICY="core.tests.unit.test_checks.NotAPolicy"):
            assert ids(check_creator_policy(None)) == ["core.E003"]

    def test_a_policy_that_cannot_be_built_without_arguments_is_caught(self):
        """Importable and a real subclass, yet still fatal on the first request.

        This is why the check instantiates rather than only importing: the
        runtime constructs it with no arguments and shares the instance, so a
        policy with a required __init__ arg passes every cheaper check and fails
        in production.
        """
        with override_settings(CREATOR_POLICY="core.tests.unit.test_checks.PolicyNeedingArguments"):
            assert ids(check_creator_policy(None)) == ["core.E004"]

    def test_an_empty_setting_is_caught_rather_than_silently_defaulted(self):
        with override_settings(CREATOR_POLICY=""):
            errors = check_creator_policy(None)

        assert ids(errors) == ["core.E001"]
        # It says how to get the default back, since "unset it" is the fix and
        # is not guessable from the error alone.
        assert "OpenCreatorPolicy" in errors[0].hint


@pytest.mark.django_db
class TestTheCheckActuallyRunsAtCheckTime:
    """Registered, not merely written — the half every test above is blind to.

    They all call `check_creator_policy` directly, which pins what it returns
    and says nothing about whether anything ever calls it. Drop the `@register()`
    decorator and all of them stay green while `manage.py check` reports no
    issues: the deploy gate this whole module exists to be simply stops existing,
    and the 500 on `/auth/me/` it was written to prevent ships exactly as before,
    after a deploy that declared itself successful.

    So these ask the framework instead, through the entry point that actually
    runs it — management commands run the system checks, which is how the Heroku
    release phase (`migrate`) fails before the dyno boots.
    """

    def test_a_broken_policy_fails_the_command_the_release_phase_runs(self):
        """The whole point: a typo in a config var is a failed deploy."""
        with override_settings(CREATOR_POLICY="deployment.policy.Typo"):
            with pytest.raises(SystemCheckError) as raised:
                call_command("check")

        # The id, so this cannot pass on somebody else's unrelated check failing.
        assert "core.E002" in str(raised.value)
        assert "CREATOR_POLICY" in str(raised.value)

    def test_the_shipped_default_does_not_fail_a_deploy_that_is_fine(self):
        """A gate that failed the standalone would be worse than no gate — it
        would be turned off, and take the real check with it."""
        call_command("check")


class TestObjectStorageIsAllOrNone:
    """The half-configured bucket — a deployment that looks healthy and is not.

    Storage being *unset* is supported: uploads are off, everything else works,
    and that is what makes a checkout runnable without an account. Storage being
    *partly* set is the trap. `MEDIA_PUBLIC_BASE_URL` still derives from the
    endpoint and bucket, so every image already stored renders, the CSP is
    correct and nothing complains — until the first person presses Upload and
    `storage._config()` raises. Nobody reads a config var again after a
    successful deploy, so the report has to arrive at deploy time.
    """

    ALL_FIVE = {
        "OBJECT_STORAGE_ENDPOINT": "https://fsn1.example-storage.com",
        "OBJECT_STORAGE_BUCKET": "a-bucket",
        "OBJECT_STORAGE_REGION": "fsn1",
        "OBJECT_STORAGE_ACCESS_KEY": "key",
        "OBJECT_STORAGE_SECRET_KEY": "secret",
    }

    def test_all_five_set_is_silent(self):
        with override_settings(**self.ALL_FIVE):
            assert check_object_storage(None) == []

    def test_none_set_is_silent_because_that_is_a_real_deployment(self):
        """A checkout with no storage account is supported, not broken."""
        with override_settings(**dict.fromkeys(self.ALL_FIVE, "")):
            assert check_object_storage(None) == []

    @pytest.mark.parametrize("forgotten", sorted(ALL_FIVE))
    def test_forgetting_any_one_of_them_is_reported(self, forgotten):
        """Each of the five, because "the obvious one" is not how a typo picks."""
        with override_settings(**{**self.ALL_FIVE, forgotten: ""}):
            issues = check_object_storage(None)

        assert len(issues) == 1
        assert issues[0].id == "core.W001"
        # The message names the one that is missing: an operator reading a
        # deploy log needs the variable, not "something is wrong with storage".
        assert forgotten in issues[0].msg

    def test_the_secret_alone_being_set_is_reported_too(self):
        """The other end of the range — one set, four missing, still not "none"."""
        with override_settings(
            **{**dict.fromkeys(self.ALL_FIVE, ""), "OBJECT_STORAGE_SECRET_KEY": "secret"}
        ):
            issues = check_object_storage(None)

        assert len(issues) == 1
        assert issues[0].id == "core.W001"

    def test_it_warns_rather_than_failing_the_deploy(self):
        """Deliberate, and the reason it is a Warning: an Error here would refuse
        to start the very no-storage checkout the setting is optional for, so it
        would be the check that gets deleted."""
        with override_settings(**{**self.ALL_FIVE, "OBJECT_STORAGE_REGION": ""}):
            call_command("check")  # does not raise SystemCheckError

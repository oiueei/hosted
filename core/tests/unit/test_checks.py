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
from django.test import override_settings

from core.checks import check_creator_policy
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

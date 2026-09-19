"""`TIME_ZONE` comes from `DJANGO_TIME_ZONE`, defaulting to UTC.

It is what "today" and "now" mean for every date rule, and the zone an hourly
space's `opening_hours` are read in — the server can only refuse a slot that
already began today if it knows the venue's clock. Same technique as
`test_database_config.py`: the settings module is re-imported under a patched
environment (with `load_dotenv` stubbed, so a developer's own `.env` can't
answer for the test), and `django.conf.settings` keeps its own copy.
"""

import importlib
import os
from unittest import mock

import config.settings.base as base_settings


def _time_zone_with(env):
    try:
        with mock.patch.dict(os.environ, env, clear=False), mock.patch("dotenv.load_dotenv"):
            if "DJANGO_TIME_ZONE" not in env:
                os.environ.pop("DJANGO_TIME_ZONE", None)
            return importlib.reload(base_settings).TIME_ZONE
    finally:
        # Outside the patch: put the module back as the real environment has it.
        importlib.reload(base_settings)


def test_the_deployment_names_its_own_time_zone():
    assert _time_zone_with({"DJANGO_TIME_ZONE": "Europe/Madrid"}) == "Europe/Madrid"


def test_unset_it_stays_utc():
    assert _time_zone_with({}) == "UTC"

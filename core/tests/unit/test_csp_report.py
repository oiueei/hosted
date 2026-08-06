"""
The CSP violation endpoint: what it logs, and what it refuses to log.

The endpoint exists so a blocked injection leaves a trace instead of failing
silently. But it accepts a POST from anyone, so the tests that matter are as
much about what it *drops* — oversized bodies, unknown fields, forged log lines
— as about the report it records.
"""

import json
import logging

import pytest
from django.test import Client
from django.urls import reverse

from core.views.csp import MAX_REPORT_BYTES

REPORT = {
    "csp-report": {
        "document-uri": "https://www.oiueei.com/collections/ABC123",
        "violated-directive": "script-src 'self'",
        "blocked-uri": "inline",
        "script-sample": "alert(1)",
    }
}


@pytest.fixture
def security_log(caplog):
    """Capture the ``security`` logger, which deliberately does not propagate.

    ``config/settings`` gives it its own handler and ``propagate: False``, so
    caplog's root handler never sees a single record from it — plain ``caplog``
    reads empty here no matter what the code does. That is worse than useless
    for the assertions below: every negative one ("this must NOT be logged")
    would pass vacuously and certify nothing. Attach caplog's own handler to the
    logger instead, and take it off again afterwards.
    """
    logger = logging.getLogger("security")
    logger.addHandler(caplog.handler)
    caplog.set_level(logging.WARNING, logger="security")
    yield caplog
    logger.removeHandler(caplog.handler)


def _post(body, content_type="application/csp-report"):
    return Client().post(
        reverse("csp-report"),
        data=body if isinstance(body, (str, bytes)) else json.dumps(body),
        content_type=content_type,
    )


@pytest.mark.django_db
def test_a_violation_is_written_to_the_security_log(security_log):
    """The whole point: a blocked script becomes a line an operator can find."""
    res = _post(REPORT)

    assert res.status_code == 204
    logged = security_log.text
    assert "CSP violation" in logged
    assert "violated-directive=script-src 'self'" in logged
    assert "blocked-uri=inline" in logged


@pytest.mark.django_db
def test_the_report_to_batch_shape_is_understood_too(security_log):
    """Browsers on the modern ``report-to`` path send a list of ``{"body": {...}}``.

    Reading only the legacy shape would mean logging nothing at all for them —
    the endpoint would look healthy while recording none of their violations.
    """
    batch = [{"type": "csp-violation", "body": {"violated-directive": "img-src"}}]

    res = _post(batch, content_type="application/reports+json")

    assert res.status_code == 204
    assert "violated-directive=img-src" in security_log.text


@pytest.mark.django_db
def test_an_oversized_body_is_dropped_without_logging(security_log):
    """The log must not be a surface an anonymous POST can write megabytes into."""
    huge = {"csp-report": {"blocked-uri": "A" * (MAX_REPORT_BYTES + 1000)}}

    res = _post(huge)

    assert res.status_code == 204
    assert "CSP violation" not in security_log.text


@pytest.mark.django_db
def test_a_long_field_is_truncated_rather_than_logged_whole(security_log):
    """Under the size cap, but still attacker-chosen: the field itself is bounded.

    Without the per-field limit a report just under MAX_REPORT_BYTES would write
    8 kB of chosen text into the log on every request the rate limit allows.
    """
    _post({"csp-report": {"blocked-uri": "B" * 2000}})

    assert "B" * 200 in security_log.text
    assert "B" * 201 not in security_log.text


@pytest.mark.django_db
def test_a_report_cannot_forge_extra_log_lines(security_log):
    """``blocked-uri`` is attacker-influenced: a newline would fake a log entry."""
    forged = {"csp-report": {"blocked-uri": "evil\nWARNING [SECURITY] Account XYZ deleted"}}

    res = _post(forged)

    assert res.status_code == 204
    # One record, and the newline is gone from it.
    assert len(security_log.records) == 1
    assert "\n" not in security_log.records[0].getMessage()


@pytest.mark.django_db
def test_unknown_fields_are_not_logged(security_log):
    """Only the known keys travel; a report can't smuggle its own payload in."""
    _post({"csp-report": {"violated-directive": "script-src", "attacker-field": "SMUGGLED"}})

    assert "SMUGGLED" not in security_log.text


@pytest.mark.django_db
@pytest.mark.parametrize("body", [b"not json at all", b"", b"[]", b'"a string"'])
def test_a_body_we_cannot_read_is_dropped_not_argued_with(body, security_log):
    """The browser is not a client we owe a 400 — an unreadable report is noise."""
    res = _post(body)

    assert res.status_code == 204
    assert "CSP violation" not in security_log.text


@pytest.mark.django_db
def test_a_get_is_not_allowed():
    """Reports are POSTs; a GET must not become a way to probe the endpoint."""
    assert Client().get(reverse("csp-report")).status_code == 405


@pytest.mark.django_db
def test_every_response_advertises_the_endpoint(client):
    """A policy that names no collector reports nothing — pin the wiring together.

    The endpoint and the directive pointing at it are one feature; a rename on
    either side that forgot the other would leave a policy reporting into a void.
    """
    res = client.get(reverse("health-check"))

    csp = res.headers["Content-Security-Policy"]
    assert f"report-uri {reverse('csp-report')}" in csp
    assert "report-to csp" in csp
    assert res.headers["Reporting-Endpoints"] == f'csp="{reverse("csp-report")}"'

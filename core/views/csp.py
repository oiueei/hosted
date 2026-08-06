"""
Where the browser reports a Content-Security-Policy violation.

The CSP is the last net under the one place this app hands the browser markup it
did not write: `MarkdownText` renders owner-authored Markdown through
`dangerouslySetInnerHTML`. If that sanitiser is ever wrong, the policy blocks
the injected script — silently. This endpoint is what turns that silence into a
line in the security log.

First-party on purpose (DESIGN §9): a hosted report collector would receive the
URL of every page a member visits, which is exactly the tracking OIUEEI promises
not to do. So the reports land here and go to the same `security` logger as the
auth events.

Two things keep it from becoming a liability of its own. Browser extensions
inject scripts into pages and generate a *lot* of false reports, so the endpoint
is rate-limited per IP and the body is capped — an attacker (or a noisy
extension) must not be able to write unbounded attacker-chosen text into the
logs. And only four known fields are logged, each truncated: the report is
attacker-influenced data, never a passthrough.
"""

import json
import logging

from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit

from core.utils import get_client_ip

security_logger = logging.getLogger("security")

# Plenty for a real violation report, small enough that the log can't be used as
# a writable surface. Anything larger is not a browser report we care about.
MAX_REPORT_BYTES = 8192

# The fields worth keeping, and how much of each. `blocked-uri` and
# `script-sample` are the attacker-influenced ones, so they are the shortest.
_FIELDS = {
    "violated-directive": 100,
    "effective-directive": 100,
    "document-uri": 200,
    "blocked-uri": 200,
    "script-sample": 100,
}


def _summarise(report):
    """A short, bounded `key=value` line from a violation report body.

    Accepts both shapes the browser may send: the legacy `report-uri` payload
    (`{"csp-report": {...}}`) and a `report-to` batch (`[{"body": {...}}, ...]`),
    of which only the first entry is summarised — the rest are almost always
    repeats of the same violation.
    """
    if isinstance(report, list):
        report = report[0].get("body", {}) if report and isinstance(report[0], dict) else {}
    if not isinstance(report, dict):
        return None
    body = report.get("csp-report", report)
    if not isinstance(body, dict):
        return None
    parts = []
    for key, limit in _FIELDS.items():
        value = body.get(key)
        if not isinstance(value, str) or not value:
            continue
        # Newlines would let a report forge extra log lines.
        clean = value.replace("\r", " ").replace("\n", " ")[:limit]
        parts.append(f"{key}={clean}")
    return " ".join(parts) or None


@csrf_exempt
@require_POST
@ratelimit(key="ip", rate="30/h", method="POST", block=True)
def csp_report(request):
    """POST /api/v1/csp-report/ — accept a CSP violation report.

    Always answers 204, whatever the body: the browser is not a client we owe an
    error to, and a report we can't parse is one to drop, not to argue with.
    A plain Django view rather than a DRF one because the browser sends
    `application/csp-report` / `application/reports+json`, which DRF's JSON
    parser would reject with a 415 before the handler ever ran.
    """
    if len(request.body) > MAX_REPORT_BYTES:
        return HttpResponse(status=204)
    try:
        report = json.loads(request.body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return HttpResponse(status=204)

    summary = _summarise(report)
    if summary:
        security_logger.warning(f"CSP violation from IP {get_client_ip(request)}: {summary}")
    return HttpResponse(status=204)

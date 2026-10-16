"""
URL configuration for OIUEEI project.
"""

import os

from django.conf import settings
from django.contrib import admin
from django.http import HttpResponse, HttpResponsePermanentRedirect
from django.urls import include, path, re_path
from django_otp.admin import OTPAdminSite
from django_ratelimit.decorators import ratelimit

from core.models import Collection
from core.services.link_preview import (
    inject_preview,
    preview_for_route,
    route_for_preview,
    site_preview,
)
from core.throttles import spend_anonymous_quota

# Require a verified OTP device (django-otp) for every admin login, on top of
# password auth. Swapping the class (rather than instantiating a fresh
# OTPAdminSite) keeps the existing instance's `name = "admin"`, so every
# `{% url 'admin:...' %}` / `reverse("admin:...")` reference still resolves.
# Bootstrap the first device via `python manage.py add_totp_device <email>`
# (django-otp's own device-config UI needs a verified login to reach it).
admin.site.__class__ = OTPAdminSite

# Throttle admin login attempts: wrap the admin site's login view with an
# IP-keyed POST rate limit so the password form can't be brute-forced. Applied
# before `admin.site.urls` is built below so get_urls() picks up the wrapper.
# (django-ratelimit on top of django-otp — no django-axes. The admin path is
# also non-default, see below.)
admin.site.login = ratelimit(key="ip", rate="5/m", method="POST", block=True)(admin.site.login)

urlpatterns = [
    path("oiueei-admin/", admin.site.urls),
    path("api/v1/", include("core.urls")),
]

# DRF login for browsable API (development only)
if settings.DEBUG:
    urlpatterns += [
        path("api-auth/", include("rest_framework.urls")),
    ]


def spa_index(request):
    """Serve the React SPA index.html for all non-API routes.

    ``Cache-Control: no-cache`` — the browser (or a CDN in front) may keep a copy
    but has to ask before reusing it. It is what makes the reload a stale tab does
    after a deploy (``reloadOnStaleChunk``) worth anything: the page names its
    JS chunks by hash, a release replaces them, and a cached ``index.html`` would
    hand the reload the very same page that names the chunks that are gone. The
    hashed assets themselves are served (and cached) by the static layer.

    A few routes get their ``<head>`` filled in for link previews (see
    ``core.services.link_preview``): a collection, a thing and a share link. Only
    what an anonymous visitor could already read on the page is used, so a private,
    inactive or unknown target is answered with the site's card, the same as any
    page. The share link carries no photo, like the endpoint behind its join page.

    A visit to one of those routes asks the database, so it spends the visitor's
    share of ``ANON_API_RATE`` — the same per-IP count the API uses
    (``core.throttles.spend_anonymous_quota``). Past the ceiling nothing is asked:
    the page carries the site's card and no card of the target, and no error — it
    is a page a person opens. A route that asks nothing spends nothing.

    Every page that gets no card of its own (the front door, the login page, any
    route the app owns, and a target that is private, inactive, unknown or
    withheld by the ceiling) gets **the site's card** instead: what OIUEEI is, in
    the deployment's language (``core.services.link_preview.site_preview``). It is
    the same bytes for all of them — its address is the site's, never the page's —
    which is what keeps a private collection indistinguishable from a code that
    names nothing, and it costs no query and spends no allowance.
    """
    return _serve_index(request)


def _serve_index(request, allowed=None):
    """``spa_index``'s body. ``allowed`` is the answer of a caller that has already
    counted this visit (``collection_address``); ``None`` means count it here."""
    index_path = os.path.join(settings.BASE_DIR, "frontend", "dist", "index.html")
    try:
        with open(index_path, encoding="utf-8") as f:
            html = f.read()
    except FileNotFoundError:
        return HttpResponse("Frontend not built. Run: cd frontend && npm run build", status=503)
    route = route_for_preview(request.path)
    preview = None
    if route:
        if allowed is None:
            allowed = spend_anonymous_quota(request) is None
        if allowed:
            preview = preview_for_route(route)
    if preview:
        html = inject_preview(html, preview, request.build_absolute_uri(request.path))
    else:
        html = inject_preview(html, site_preview(), request.build_absolute_uri("/"))
    response = HttpResponse(html, content_type="text/html")
    response["Cache-Control"] = "no-cache"
    return response


def collection_address(request, prefix, code, rest=None):
    """A collection lives at ``/{kind}/{code}``; any other prefix is sent there.

    ``/collections/{code}`` was the only address before kinds, and an old link — an
    email, a pinned page — may still name it, or the wrong kind. The 301 keeps the
    rest of the path and the query string (``?thing=…`` of the join page), and is
    safe to cache because a collection's kind never changes. A code that names no
    collection, or one already under its own prefix, is the SPA's page as usual.

    It deliberately asks nothing about permissions: an old link to a private
    collection has to reach its page so the member can sign in. What it tells a
    stranger is the kind of a collection whose code they already hold — that the
    code exists is already said by ``GET /api/v1/collections/{code}/``, 403 against
    404 — and what the link preview serves for the page itself is unchanged: the
    body of a private collection is still the site's card, the same as for a code
    that names nothing; the difference is only the redirect.

    The lookup spends the visitor's share of ``ANON_API_RATE`` (the API's own
    per-IP count). Past the ceiling it asks nothing and redirects nothing: the page
    is served as it is, and the SPA moves the address itself
    (``useCanonicalCollectionPath``). One visit is one unit: the page it hands on to
    is not counted again.
    """
    allowed = spend_anonymous_quota(request) is None
    if not allowed:
        return _serve_index(request, allowed=False)
    kind = Collection.objects.filter(code=code).values_list("kind", flat=True).first()
    if kind is None or prefix == kind.lower():
        return _serve_index(request, allowed=True)
    target = f"/{kind.lower()}/{code}{rest or ''}"
    if request.META.get("QUERY_STRING"):
        target += f"?{request.META['QUERY_STRING']}"
    return HttpResponsePermanentRedirect(target)


def deployment_urlpatterns():
    """Mount the URL modules this deployment adds (`DEPLOYMENT_URLCONFS`).

    Empty in the standalone: every route the product serves is already in
    `core.urls`. A deployment that adds views of its own — an operator's service
    layer, a self-hoster's intranet page — names the module in the setting
    rather than editing this file, which is what lets those routes survive an
    upgrade instead of being re-applied by hand each time.

    **They mount before the SPA catch-all below, and that ordering is the whole
    point.** The catch-all spares only `static/`, `api/` and the admin prefix,
    so a deployment route outside those — a plain Django page at
    `/request-access/`, say — would otherwise be swallowed and answered with
    `index.html`: a 200 carrying the wrong page, which is worse to diagnose than
    a 404 because nothing about it looks broken.
    """
    return [path("", include(module)) for module in settings.DEPLOYMENT_URLCONFS]


urlpatterns += deployment_urlpatterns()

# A collection's address follows its kind, and the pre-kind /collections/ one moves.
urlpatterns += [
    re_path(r"^collections/new/?$", lambda request: HttpResponsePermanentRedirect("/new")),
    re_path(
        r"^(?P<prefix>collections|stall|library|shed)/"
        r"(?P<code>[A-Za-z0-9]{6})(?P<rest>/.*)?$",
        collection_address,
    ),
]

# Catch-all: serve React SPA for all routes not handled above
urlpatterns += [re_path(r"^(?!static/|api/|oiueei-admin).*", spa_index)]

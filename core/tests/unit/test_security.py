"""
Unit tests for OIUEEI security features.
"""

import string

import pytest
from django.test import Client, RequestFactory, override_settings

from core.middleware import SecurityHeadersMiddleware
from core.utils import UNKNOWN_CLIENT_IP, generate_id, get_client_ip, redact_email


class TestSecureIdGeneration:
    """Tests for cryptographically secure ID generation."""

    def test_generate_id_length(self):
        """ID should be exactly 6 characters."""
        for _ in range(100):
            assert len(generate_id()) == 6

    def test_generate_id_characters(self):
        """ID should only contain uppercase letters and digits."""
        valid_chars = set(string.ascii_uppercase + string.digits)
        for _ in range(100):
            id_ = generate_id()
            assert all(c in valid_chars for c in id_)

    def test_generate_id_uniqueness(self):
        """IDs should be unique (statistically unlikely to collide in 1000 attempts)."""
        ids = set(generate_id() for _ in range(1000))
        # With 36^6 = 2.17 billion possibilities, 1000 IDs should be unique
        assert len(ids) == 1000

    def test_generate_id_uses_secrets_module(self):
        """Verify that secrets module is used (via inspection)."""
        import inspect

        from core import utils

        source = inspect.getsource(utils.generate_id)
        assert "secrets.choice" in source
        assert "random.choice" not in source


class TestGetClientIp:
    """Tests for get_client_ip() — ensures IP-based rate limiting cannot be spoofed."""

    def setup_method(self):
        self.factory = RequestFactory()

    def test_returns_remote_addr_when_no_forwarded_header(self):
        request = self.factory.get("/")
        request.META["REMOTE_ADDR"] = "1.2.3.4"
        assert get_client_ip(request) == "1.2.3.4"

    def test_returns_last_ip_from_forwarded_header(self):
        """Heroku appends the real client IP at the end — must take the last value."""
        request = self.factory.get("/")
        request.META["HTTP_X_FORWARDED_FOR"] = "10.0.0.1, 8.8.4.4"
        assert get_client_ip(request) == "8.8.4.4"

    def test_spoofed_first_ip_is_ignored(self):
        """An attacker injecting a fake IP at position 0 should not affect rate limiting."""
        request = self.factory.get("/")
        request.META["HTTP_X_FORWARDED_FOR"] = "0.0.0.1, 5.6.7.8"
        assert get_client_ip(request) == "5.6.7.8"

    def test_single_ip_in_forwarded_header(self):
        request = self.factory.get("/")
        request.META["HTTP_X_FORWARDED_FOR"] = "9.9.9.9"
        assert get_client_ip(request) == "9.9.9.9"

    def test_whitespace_stripped_from_ip(self):
        request = self.factory.get("/")
        request.META["HTTP_X_FORWARDED_FOR"] = "1.1.1.1,  2.2.2.2 "
        assert get_client_ip(request) == "2.2.2.2"

    def test_falls_back_to_unknown_when_no_remote_addr(self):
        request = self.factory.get("/")
        request.META.pop("REMOTE_ADDR", None)
        request.META.pop("HTTP_X_FORWARDED_FOR", None)
        assert get_client_ip(request) == UNKNOWN_CLIENT_IP

    def test_ipv6_client_is_accepted(self):
        request = self.factory.get("/")
        request.META["HTTP_X_FORWARDED_FOR"] = "2001:db8::1"
        assert get_client_ip(request) == "2001:db8::1"

    def test_unparseable_forwarded_value_falls_back_to_remote_addr(self):
        """A non-IP would reach ipaddress.ip_network() inside django-ratelimit and
        raise ValueError there — a 500 from the decorator, before the view runs.
        The rate limit still has to happen, so we fall back rather than trust it."""
        request = self.factory.get("/")
        request.META["REMOTE_ADDR"] = "3.3.3.3"
        request.META["HTTP_X_FORWARDED_FOR"] = "not-an-ip"
        assert get_client_ip(request) == "3.3.3.3"

    def test_unparseable_everything_buckets_together(self):
        """Nothing parseable anywhere still has to yield a usable bucket key, and a
        *shared* one: an unidentifiable caller must not get a fresh allowance."""
        request = self.factory.get("/")
        request.META["REMOTE_ADDR"] = "garbage"
        request.META["HTTP_X_FORWARDED_FOR"] = "also-garbage"
        assert get_client_ip(request) == UNKNOWN_CLIENT_IP

    @override_settings(TRUSTED_PROXY_COUNT=0)
    def test_forwarded_header_is_ignored_when_no_proxy_is_trusted(self):
        """The whole point of the setting: a deployment terminating connections
        itself must not read a header the caller wrote, or one caller mints a
        fresh rate-limit bucket per request and every IP limit stops holding."""
        request = self.factory.get("/")
        request.META["REMOTE_ADDR"] = "4.4.4.4"
        request.META["HTTP_X_FORWARDED_FOR"] = "1.2.3.4"
        assert get_client_ip(request) == "4.4.4.4"

    @override_settings(TRUSTED_PROXY_COUNT=2)
    def test_two_trusted_hops_skips_the_cdns_own_entry(self):
        """A CDN in front of the platform router: the client is second from the
        right, because both proxies appended after it."""
        request = self.factory.get("/")
        request.META["HTTP_X_FORWARDED_FOR"] = "spoofed, 7.7.7.7, 10.0.0.9"
        assert get_client_ip(request) == "7.7.7.7"

    @override_settings(TRUSTED_PROXY_COUNT=2)
    def test_chain_shorter_than_the_trusted_hops_falls_back(self):
        """Fewer entries than trusted proxies means the request didn't come
        through them — there is no entry we may believe, so use REMOTE_ADDR."""
        request = self.factory.get("/")
        request.META["REMOTE_ADDR"] = "6.6.6.6"
        request.META["HTTP_X_FORWARDED_FOR"] = "1.2.3.4"
        assert get_client_ip(request) == "6.6.6.6"


class TestRateLimitClientIp:
    """django-ratelimit must bucket per REAL client IP, not the shared Heroku
    router REMOTE_ADDR. Guards the RATELIMIT_IP_META_KEY wiring so the
    anti-spoof get_client_ip() is actually used by the limiter (not only logging)."""

    def setup_method(self):
        self.factory = RequestFactory()

    def test_setting_points_to_anti_spoof_helper(self):
        """The limiter's IP key must resolve to core.utils.get_client_ip."""
        from django.conf import settings
        from django.utils.module_loading import import_string

        assert settings.RATELIMIT_IP_META_KEY == "core.utils.get_client_ip"
        assert import_string(settings.RATELIMIT_IP_META_KEY) is get_client_ip

    def test_ratelimit_resolves_ip_via_rightmost_forwarded_for(self):
        """The limiter's IP resolver must use the rightmost X-Forwarded-For (the
        real client appended by the Heroku router), never REMOTE_ADDR (the shared
        router address) nor an attacker-spoofed leading value."""
        from django_ratelimit.core import _get_ip

        request = self.factory.post("/")
        request.META["REMOTE_ADDR"] = "10.0.0.1"  # shared router IP — must NOT be the bucket key
        request.META["HTTP_X_FORWARDED_FOR"] = "6.6.6.6, 203.0.113.7"  # spoofed, real-client
        assert _get_ip(request) == "203.0.113.7"

    def test_limiter_survives_a_forwarded_header_that_is_not_an_ip(self):
        """django-ratelimit feeds our return value to ipaddress.ip_network(), so
        anything unparseable raised ValueError *inside the decorator* — a 500 on
        every rate-limited endpoint (request-link, join, contact, csp-report,
        the admin login) from one header, before the view ever ran."""
        from django_ratelimit.core import _get_ip

        request = self.factory.post("/")
        request.META["REMOTE_ADDR"] = "203.0.113.9"
        request.META["HTTP_X_FORWARDED_FOR"] = "'; DROP TABLE users; --"
        assert _get_ip(request) == "203.0.113.9"


class TestSecurityHeadersMiddleware:
    """Tests for SecurityHeadersMiddleware — CSP and Permissions-Policy headers."""

    def setup_method(self):
        self.factory = RequestFactory()
        self.middleware = SecurityHeadersMiddleware(
            get_response=lambda r: __import__(
                "django.http", fromlist=["HttpResponse"]
            ).HttpResponse()
        )

    def test_csp_header_is_present(self):
        request = self.factory.get("/")
        response = self.middleware(request)
        assert "Content-Security-Policy" in response

    def test_permissions_policy_header_is_present(self):
        request = self.factory.get("/")
        response = self.middleware(request)
        assert "Permissions-Policy" in response

    def test_csp_blocks_frame_ancestors(self):
        request = self.factory.get("/")
        response = self.middleware(request)
        assert "frame-ancestors 'none'" in response["Content-Security-Policy"]

    def test_csp_restricts_default_src_to_self(self):
        request = self.factory.get("/")
        response = self.middleware(request)
        assert "default-src 'self'" in response["Content-Security-Policy"]

    def test_csp_allows_images_from_the_configured_media_host(self, settings):
        """Derived from the setting, not hardcoded — prod and dev use different buckets."""
        settings.MEDIA_PUBLIC_BASE_URL = "https://a-bucket.fsn1.example-storage.com"
        csp = self.middleware(self.factory.get("/"))["Content-Security-Policy"]
        img = next(d for d in csp.split(";") if d.strip().startswith("img-src"))
        assert "https://a-bucket.fsn1.example-storage.com" in img

    def test_csp_allows_uploading_to_the_media_host(self, settings):
        """The upload is a fetch() straight to the bucket, so connect-src must allow it."""
        settings.MEDIA_PUBLIC_BASE_URL = "https://a-bucket.fsn1.example-storage.com"
        csp = self.middleware(self.factory.get("/"))["Content-Security-Policy"]
        connect = next(d for d in csp.split(";") if d.strip().startswith("connect-src"))
        assert "https://a-bucket.fsn1.example-storage.com" in connect

    def test_csp_lets_a_cdn_deployment_still_reach_its_bucket(self, settings):
        """The regression this pair exists for.

        Reads may be pointed at a CDN; an upload cannot follow them there. A
        presigned URL is signed for the bucket's own virtual host, so a policy
        that names only the read origin forbids the PUT — and does it invisibly,
        because the images already in the bucket go on loading through the CDN
        while every new upload dies in the browser.
        """
        settings.MEDIA_PUBLIC_BASE_URL = "https://media.example.com"
        settings.OBJECT_STORAGE_PUBLIC_URL = "https://a-bucket.fsn1.example-storage.com"
        csp = self.middleware(self.factory.get("/"))["Content-Security-Policy"]

        connect = next(d for d in csp.split(";") if d.strip().startswith("connect-src"))
        assert "https://a-bucket.fsn1.example-storage.com" in connect, (
            "connect-src must name the bucket the presigned PUT actually goes to"
        )
        assert "https://media.example.com" in connect

    def test_csp_does_not_let_the_bucket_serve_images_a_cdn_is_fronting(self, settings):
        """The other half: `img-src` follows the reads, and only the reads.

        Widening it to the bucket as well would be a policy that allows an origin
        nothing is asked to render from — the "while we're in here" habit that
        turns a CSP into decoration.
        """
        settings.MEDIA_PUBLIC_BASE_URL = "https://media.example.com"
        settings.OBJECT_STORAGE_PUBLIC_URL = "https://a-bucket.fsn1.example-storage.com"
        csp = self.middleware(self.factory.get("/"))["Content-Security-Policy"]

        img = next(d for d in csp.split(";") if d.strip().startswith("img-src"))
        assert "https://media.example.com" in img
        assert "a-bucket" not in img

    def test_csp_names_one_host_once_when_reads_and_writes_share_it(self, settings):
        """The default deployment: both settings are the bucket, so it appears once."""
        bucket = "https://a-bucket.fsn1.example-storage.com"
        settings.MEDIA_PUBLIC_BASE_URL = bucket
        settings.OBJECT_STORAGE_PUBLIC_URL = bucket
        csp = self.middleware(self.factory.get("/"))["Content-Security-Policy"]

        connect = next(d for d in csp.split(";") if d.strip().startswith("connect-src"))
        assert connect.count(bucket) == 1, f"duplicated origin: {connect!r}"

    def test_csp_takes_the_origin_only_not_a_path(self, settings):
        """A path is not something CSP matches on; leaving one in widens nothing but lies."""
        settings.MEDIA_PUBLIC_BASE_URL = "https://cdn.example.org/media/v2"
        settings.OBJECT_STORAGE_PUBLIC_URL = ""
        csp = self.middleware(self.factory.get("/"))["Content-Security-Policy"]
        assert "https://cdn.example.org;" in csp or "https://cdn.example.org " in csp
        assert "/media/v2" not in csp

    def test_csp_names_no_host_when_none_is_configured(self, settings):
        """An unconfigured checkout must not widen its policy to a stray empty token."""
        settings.MEDIA_PUBLIC_BASE_URL = ""
        settings.OBJECT_STORAGE_PUBLIC_URL = ""
        csp = self.middleware(self.factory.get("/"))["Content-Security-Policy"]
        assert "img-src 'self' blob:;" in csp
        assert "connect-src 'self';" in csp

    def test_csp_no_longer_names_cloudinary(self, settings):
        """The bucket replaced it; a leftover allowance is a wider policy for nothing."""
        assert "cloudinary" not in self.middleware(self.factory.get("/"))["Content-Security-Policy"]

    def test_permissions_policy_disables_sensitive_apis(self):
        request = self.factory.get("/")
        response = self.middleware(request)
        policy = response["Permissions-Policy"]
        assert "camera=()" in policy
        assert "microphone=()" in policy
        assert "geolocation=()" in policy

    def test_csp_includes_hardening_directives(self):
        """object-src/base-uri/form-action block plugin embedding, base-tag
        injection, and cross-origin form hijacking respectively."""
        request = self.factory.get("/")
        response = self.middleware(request)
        csp = response["Content-Security-Policy"]
        assert "object-src 'none'" in csp
        assert "base-uri 'self'" in csp
        assert "form-action 'self'" in csp


class TestRedactEmail:
    """M5: emails are reduced to a stable, non-reversible tag for logs."""

    def test_redacts_to_stable_non_reversible_tag(self):
        tag = redact_email("Lala@Disroot.ORG")
        assert tag.startswith("email#")
        # The address (local part + domain) never appears.
        assert "lala" not in tag.lower()
        assert "disroot" not in tag.lower()
        # Stable + case/whitespace-insensitive, so events for one user correlate.
        assert tag == redact_email(" lala@disroot.org ")
        # Distinct emails produce distinct tags; empty is handled.
        assert tag != redact_email("other@disroot.org")
        assert redact_email("") == "email#none"


@pytest.mark.django_db
def test_admin_login_page_still_loads():
    """M3: wrapping the admin login with a POST rate limit must not break the
    login page — a GET still renders (the limit only throttles POST attempts)."""
    resp = Client().get("/oiueei-admin/login/")
    assert resp.status_code == 200
    # 200 alone could be an error page — the actual login form must render.
    assert b'name="username"' in resp.content


@pytest.mark.django_db
class TestAuthCookiesFollowTheProjectsCookieSwitch:
    """The JWT cookies read `SESSION_COOKIE_SECURE`, not `DEBUG`.

    They are the credentials — an access token and a 7-day refresh token — and
    they used to derive `Secure` from `not DEBUG`. That is right for both
    environments this repo ships and wrong for one neither is: `DEBUG=True`
    behind HTTPS served these two cookies without the flag while the session and
    CSRF cookies beside them kept it. Invisible in the app; the whole difference
    is what a downgraded request carries in clear.
    """

    def _login(self, client):
        from core.models import RSVP, User

        user = User.objects.create(code="CKY001", email="cookie@example.com")
        rsvp = RSVP.objects.create(user_code=user, user_email=user.email)
        return client.get(f"/api/v1/auth/verify/{rsvp.token}/")

    def test_a_deployment_with_secure_cookies_gets_secure_auth_cookies(self, api_client, settings):
        # DEBUG stays True (the test settings): the point is that it is no longer
        # what decides, so this pairing has to produce Secure cookies.
        settings.DEBUG = True
        settings.SESSION_COOKIE_SECURE = True

        res = self._login(api_client)

        assert res.status_code == 200
        assert res.cookies["access_token"]["secure"]
        assert res.cookies["refresh_token"]["secure"]

    def test_plain_http_development_still_gets_usable_cookies(self, api_client, settings):
        """The other half: a Secure cookie on http://localhost is never sent
        back, so flipping this unconditionally would break local development."""
        settings.SESSION_COOKIE_SECURE = False

        res = self._login(api_client)

        assert res.status_code == 200
        assert not res.cookies["access_token"]["secure"]

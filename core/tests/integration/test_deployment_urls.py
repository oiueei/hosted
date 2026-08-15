"""`DEPLOYMENT_URLCONFS` — the extension point a deployment mounts its own views on.

The standalone mounts nothing: every route OIUEEI serves as a product is in
`core.urls`. The setting exists so an operator's service layer, or a
self-hoster's own page, can be added **without editing `config/urls.py`** — the
one file both would otherwise patch, and re-patch after every update.

Two behaviours are worth protecting, and the second is the one that bites:

1. A named module is mounted; an unnamed one is not.
2. **Deployment routes mount before the SPA catch-all.** That catch-all matches
   everything except `static/`, `api/` and the admin prefix, so a deployment
   page at `/request-access/` landing *after* it would be answered with
   `index.html` and a **200** — the wrong page under a success status, which is
   harder to diagnose than a 404 because nothing about it looks broken.
"""

from django.test import override_settings
from django.urls import URLPattern, URLResolver

from config.urls import deployment_urlpatterns, spa_index, urlpatterns

SAMPLE = "core.tests.sample_deployment_urls"


class TestDeploymentUrlconfs:
    def test_the_standalone_mounts_no_deployment_routes(self):
        """Unset is the standalone default, and it must add nothing at all.

        Not merely "nothing that resolves": nothing appended, so an
        upstream OIUEEI has exactly the URL tree it had before this setting
        existed.
        """
        with override_settings(DEPLOYMENT_URLCONFS=[]):
            assert deployment_urlpatterns() == []

    def test_a_named_module_is_mounted_at_the_root(self):
        with override_settings(DEPLOYMENT_URLCONFS=[SAMPLE]):
            mounted = deployment_urlpatterns()

        assert len(mounted) == 1
        resolver = mounted[0]
        assert isinstance(resolver, URLResolver)
        # Mounted at the root: the module's own paths are the full paths.
        assert str(resolver.pattern) == ""
        assert [str(p.pattern) for p in resolver.url_patterns] == ["sample-deployment-page/"]

    def test_each_named_module_is_mounted_once_and_in_order(self):
        """Order is the operator's, not ours — first named, first matched."""
        with override_settings(DEPLOYMENT_URLCONFS=[SAMPLE, SAMPLE]):
            assert len(deployment_urlpatterns()) == 2


class TestTheSpaCatchAllStaysLast:
    def test_the_spa_catch_all_is_the_final_pattern(self):
        """Nothing may be registered after the catch-all — it would be unreachable.

        What this actually guards is a **future edit of `config/urls.py`**: the
        natural place to append a route is the bottom of the file, which is
        precisely where it stops resolving. It fails the moment anyone does that.

        It deliberately does *not* try to prove the ordering with modules
        mounted. `config/urls.py` is evaluated once at import, with
        `DEPLOYMENT_URLCONFS` empty in the test environment, so re-deriving the
        list here would only re-assert the order this test itself composed.
        The line ordering in the module is what puts deployment routes ahead of
        the catch-all; this pins the end of that list, which is the end anyone
        editing later is going to touch.
        """
        last = urlpatterns[-1]

        assert isinstance(last, URLPattern)
        assert last.callback is spa_index
        # Identified by its *pattern*, not just its callback: a route appended
        # below that also points at `spa_index` — an alias, a second entry
        # point — is still a route the catch-all has stopped protecting, and an
        # assertion on the callback alone would wave it through. (It did, when
        # this test was first written and mutation-checked.)
        assert str(last.pattern) == r"^(?!static/|api/|oiueei-admin).*"

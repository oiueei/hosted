"""Routes this deployment adds, mounted through `DEPLOYMENT_URLCONFS`.

They are declared here rather than in `config/urls.py` so that file — which
upstream owns and evolves — is never edited here. See SELF_HOSTING.md §1.
"""

from django.urls import path
from django.views.generic import RedirectView

from .views import PopInView, RequestAccessView

app_name = "hosted"

urlpatterns = [
    # The historical path, kept exactly: it is in emails, in printed QR codes and
    # in whatever people bookmarked. Upstream renamed the endpoint it used to
    # share to /auth/join/ when the open door left the standalone; here the old
    # URL goes on answering, served by the view that actually does the old thing.
    path("api/v1/auth/pop-in/", PopInView.as_view(), name="pop-in"),
    # A plain Django page, outside the SPA. It mounts above the catch-all (see
    # config/urls.py), which is the only reason a non-api/ path answers at all.
    path("request-access/", RequestAccessView.as_view(), name="request-access"),
    # The slash-less typo, caught on purpose. Django's own APPEND_SLASH redirect
    # never gets a chance to fix this one: it only fires when a URL fails to
    # resolve to anything, and `/request-access` *does* resolve — to the SPA
    # catch-all in config/urls.py, which matches everything outside static/,
    # api/ and the admin prefix and answers 200 with index.html. React Router
    # then takes over client-side, and its `/:userCode` public-profile route is
    # declared ahead of this deployment's own routes, so it claims
    # "request-access" as a user code and calls
    # `GET /api/v1/users/request-access/` — the 404 an operator actually sees,
    # two layers away from the missing slash that caused it. An explicit
    # redirect here wins the race against the catch-all, because this urlconf
    # is mounted before it (see config/urls.py::deployment_urlpatterns).
    path(
        "request-access",
        RedirectView.as_view(pattern_name="hosted:request-access", permanent=True),
    ),
]

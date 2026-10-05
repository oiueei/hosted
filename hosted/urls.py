"""Routes this deployment adds, mounted through `DEPLOYMENT_URLCONFS`.

They are declared here rather than in `config/urls.py` so that file — which
upstream owns and evolves — is never edited here. See SELF_HOSTING.md §1.
"""

from django.urls import path

from .views import PopInView, RequestAccessRedirect

app_name = "hosted"

urlpatterns = [
    # The historical path, kept exactly: it is in emails, in printed QR codes and
    # in whatever people bookmarked. Upstream renamed the endpoint it used to
    # share to /auth/join/ when the open door left the standalone; here the old
    # URL goes on answering, served by the view that actually does the old thing.
    path("api/v1/auth/pop-in/", PopInView.as_view(), name="pop-in"),
    # The old address of "Request access", now a Tally form: see the view. Both spellings
    # are declared, and the slash-less one on purpose — Django's APPEND_SLASH never rescues
    # it, because `/request-access` *does* resolve (to the SPA catch-all in config/urls.py,
    # which matches everything outside static/, api/ and the admin prefix), and React Router
    # then reads it as a user code and calls `GET /api/v1/users/request-access/`: a 404 two
    # layers away from the missing slash. This urlconf is mounted before the catch-all
    # (config/urls.py::deployment_urlpatterns), so these win.
    path("request-access/", RequestAccessRedirect.as_view(), name="request-access"),
    path("request-access", RequestAccessRedirect.as_view(), name="request-access-no-slash"),
]

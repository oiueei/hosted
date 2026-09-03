"""Routes this deployment adds, mounted through `DEPLOYMENT_URLCONFS`.

They are declared here rather than in `config/urls.py` so that file — which
upstream owns and evolves — is never edited here. See SELF_HOSTING.md §1.
"""

from django.urls import path

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
]

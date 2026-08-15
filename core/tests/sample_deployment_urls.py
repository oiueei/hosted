"""A sample deployment URLconf, mounted by `integration/test_deployment_urls.py`.

Not a test module — pytest only collects `test_*` — but the *input* to one:
`DEPLOYMENT_URLCONFS` takes dotted paths to real importable modules, so proving
that a named module actually mounts needs a real one to name.

The path it serves sits outside `static/`, `api/` and the admin prefix on
purpose. Those three are the only ones the SPA catch-all spares, so this is
exactly the shape of route that the ordering in `config/urls.py` exists to
protect — anything else would pass the test without exercising the reason it
was written.
"""

from django.http import HttpResponse
from django.urls import path


def sample_page(request):
    return HttpResponse("mounted")


urlpatterns = [path("sample-deployment-page/", sample_page)]

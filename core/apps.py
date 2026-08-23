from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"

    def ready(self):
        # `checks` registers the deploy-time checks for the two settings a
        # deployment points at its own code (both resolve lazily at runtime, so
        # without them a typo in either config var reaches a booted dyno);
        # `asset_cleanup` registers the post_delete signal handlers.
        from core import checks  # noqa: F401
        from core.services import asset_cleanup  # noqa: F401

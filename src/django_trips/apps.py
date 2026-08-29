from django.apps import AppConfig


class DjangoTripsConfig(AppConfig):
    name = "django_trips"
    verbose_name = "Django Trips"
    # Pinned per-app so this package's models always get BigAutoField
    # regardless of the consuming project's own DEFAULT_AUTO_FIELD (e.g.
    # destipak's is plain AutoField) — matches the actual bigint columns
    # already in the database.
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        import django_trips.signals  # noqa: F401 pylint:disable=unused-import,import-outside-toplevel,cyclic-import

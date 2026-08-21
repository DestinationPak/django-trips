"""
Adapter for reading Location fields, so callers work the same way
whether django_trips.Location or a swapped-in model backs the FK
(DJANGO_TRIPS_LOCATION_MODEL).
"""

from django.conf import settings
from django.utils.module_loading import import_string

from django_trips.utils import resolve_media_url

DEFAULT_LOCATION_ADAPTER = "django_trips.location_adapter.LocationAdapter"


class LocationAdapter:
    """
    Reads the fields django_trips' own code needs off a Location instance.

    The default implementation assumes django_trips' own Location model's
    shape (name, slug, lat, lon, type, region, travel_tips, importance,
    poster_image/poster_url). An installer that swaps
    DJANGO_TRIPS_LOCATION_MODEL to a differently-shaped model must also set
    DJANGO_TRIPS_LOCATION_ADAPTER to a subclass overriding whichever of
    these a plain attribute read on their own model can't satisfy.
    """

    def get_name(self, location):
        return location.name

    def get_slug(self, location):
        return location.slug

    def get_lat(self, location):
        return location.lat

    def get_lon(self, location):
        return location.lon

    def get_type_display(self, location):
        return location.get_type_display()

    def get_region(self, location):
        return location.region

    def get_travel_tips(self, location):
        return location.travel_tips

    def get_importance(self, location):
        return location.importance

    def get_poster(self, location, context=None):
        return resolve_media_url(location.poster_image, location.poster_url, context or {})


def get_location_adapter():
    """Returns an instance of the configured LocationAdapter (the default
    one unless DJANGO_TRIPS_LOCATION_ADAPTER overrides it)."""
    path = getattr(settings, "DJANGO_TRIPS_LOCATION_ADAPTER", DEFAULT_LOCATION_ADAPTER)
    adapter_class = import_string(path)
    return adapter_class()

"""
P9.2 regression coverage: Location's swappable-model wiring and the
LocationAdapter contract callers read it through.
"""

from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from django_trips.choices import LocationType
from django_trips.location_adapter import LocationAdapter, get_location_adapter
from django_trips.models import (
    Location,
    get_active_locations_queryset,
    get_location_model,
    location_model_supports_hierarchy,
)
from django_trips.tests.factories import LocationFactory


class StubLocationAdapter(LocationAdapter):
    """Importable-by-dotted-path stand-in for testing the
    DJANGO_TRIPS_LOCATION_ADAPTER override - import_string() can't resolve
    a class defined inside a test method's local scope."""


class LocationSwappableTestCase(TestCase):
    def test_location_meta_swappable_setting_name(self):
        self.assertEqual(Location._meta.swappable, "DJANGO_TRIPS_LOCATION_MODEL")

    def test_unswapped_by_default(self):
        self.assertIsNone(Location._meta.swapped)

    def test_get_location_model_returns_location_by_default(self):
        self.assertIs(get_location_model(), Location)

    def test_get_active_locations_queryset_uses_active_when_available(self):
        active = LocationFactory(is_active=True)
        inactive = LocationFactory(is_active=False)

        results = list(get_active_locations_queryset())

        self.assertIn(active, results)
        self.assertNotIn(inactive, results)

    def test_get_active_locations_queryset_falls_back_without_active(self):
        """A swapped-in model isn't guaranteed to define .active() - this
        must degrade to .all() rather than raising."""
        swapped_model = MagicMock()
        swapped_model.objects = MagicMock(spec=["all"])
        with patch(
            "django_trips.models.get_location_model", return_value=swapped_model
        ):
            get_active_locations_queryset()

        swapped_model.objects.all.assert_called_once()

    def test_location_model_supports_hierarchy_true_by_default(self):
        self.assertTrue(location_model_supports_hierarchy())

    def test_location_model_supports_hierarchy_false_without_parent_and_type(self):
        id_field, name_field = MagicMock(), MagicMock()
        id_field.name = "id"
        name_field.name = "name"
        swapped_model = MagicMock()
        swapped_model._meta.get_fields.return_value = [id_field, name_field]
        with patch(
            "django_trips.models.get_location_model", return_value=swapped_model
        ):
            self.assertFalse(location_model_supports_hierarchy())


class LocationAdapterTestCase(TestCase):
    def setUp(self):
        self.parent = LocationFactory(
            name="Gilgit-Baltistan", type=LocationType.PROVINCE
        )
        self.location = LocationFactory(
            name="Hunza",
            type=LocationType.CITY,
            parent=self.parent,
            lat=36.3167,
            lon=74.65,
            importance=1.5,
        )
        self.adapter = LocationAdapter()

    def test_get_name(self):
        self.assertEqual(self.adapter.get_name(self.location), "Hunza")

    def test_get_slug(self):
        self.assertEqual(self.adapter.get_slug(self.location), self.location.slug)

    def test_get_lat_and_lon(self):
        self.assertEqual(self.adapter.get_lat(self.location), 36.3167)
        self.assertEqual(self.adapter.get_lon(self.location), 74.65)

    def test_get_type_display(self):
        self.assertEqual(self.adapter.get_type_display(self.location), "City")

    def test_get_region_from_parent(self):
        self.assertEqual(self.adapter.get_region(self.location), "Gilgit-Baltistan")

    def test_get_travel_tips(self):
        self.assertEqual(
            self.adapter.get_travel_tips(self.location), self.location.travel_tips
        )

    def test_get_importance(self):
        self.assertEqual(self.adapter.get_importance(self.location), 1.5)

    def test_get_poster_with_neither_image_nor_url_returns_none(self):
        self.assertIsNone(self.adapter.get_poster(self.location, {}))


class GetLocationAdapterTestCase(TestCase):
    def test_defaults_to_location_adapter(self):
        adapter = get_location_adapter()
        self.assertIsInstance(adapter, LocationAdapter)

    def test_honors_django_trips_location_adapter_override(self):
        with override_settings(
            DJANGO_TRIPS_LOCATION_ADAPTER=(
                "django_trips.tests.test_location_adapter.StubLocationAdapter"
            )
        ):
            adapter = get_location_adapter()

        self.assertIsInstance(adapter, StubLocationAdapter)

"""
Coverage for AbstractLocation - the base class Location itself now
extends, and that an installer can extend to build a custom Location
model without writing a LocationAdapter.
"""

from django.test import TestCase
from django.test.utils import isolate_apps

from django_trips.choices import LocationType
from django_trips.models import AbstractLocation, Location


class AbstractLocationTestCase(TestCase):
    def test_abstract_location_is_abstract(self):
        self.assertTrue(AbstractLocation._meta.abstract)

    def test_location_inherits_abstract_location(self):
        self.assertTrue(issubclass(Location, AbstractLocation))

    def test_location_is_still_concrete_and_swappable(self):
        self.assertFalse(Location._meta.abstract)
        self.assertEqual(Location._meta.swappable, "DJANGO_TRIPS_LOCATION_MODEL")

    @isolate_apps("django_trips")
    def test_custom_subclass_gets_fields_and_methods_for_free(self):
        class CustomLocation(AbstractLocation):
            class Meta:
                app_label = "django_trips"

        province = CustomLocation(name="Gilgit-Baltistan", type=LocationType.PROVINCE)
        city = CustomLocation(name="Hunza", type=LocationType.CITY, parent=province)

        self.assertEqual(str(city), "Hunza")
        self.assertEqual(city.region, "Gilgit-Baltistan")
        self.assertIsNone(CustomLocation(name="Orphan").region)

    @isolate_apps("django_trips")
    def test_custom_subclass_can_override_a_single_method(self):
        class CustomLocation(AbstractLocation):
            class Meta:
                app_label = "django_trips"

            def get_lat_lng(self):
                return self.lat, self.lon

        instance = CustomLocation(name="Skardu", lat=35.3, lon=75.6)

        self.assertEqual(instance.get_lat_lng(), (35.3, 75.6))

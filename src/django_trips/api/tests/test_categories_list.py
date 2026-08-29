"""Tests for the public categories/activities listing endpoint."""

import pytest
from django.urls import reverse

from django_trips.tests.factories import (
    AuthenticatedUserTestCase,
    CategoryFactory,
    TripFactory,
)


@pytest.mark.django_db
class TestCategoriesListAPI(AuthenticatedUserTestCase):
    url = reverse("trips-api:categories")

    def get_categories(self):
        response = self.client.get(self.url, {}, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        return {item["name"]: item for item in response.json()["results"]}

    def test_without_authentication(self):
        """Categories listing is public - no authentication required."""
        response = self.client.get(self.url, {}, headers={})
        self.assertEqual(response.status_code, 200)

    def test_trips_count_reflects_active_trips_only(self):
        trekking = CategoryFactory(name="Trekking")
        TripFactory.create_batch(
            2, categories=["Trekking"], is_active=True, trip_schedule=None
        )
        TripFactory(categories=["Trekking"], is_active=False, trip_schedule=None)

        categories = self.get_categories()
        self.assertEqual(categories["Trekking"]["trips_count"], 2)
        self.assertEqual(categories["Trekking"]["slug"], trekking.slug)

    def test_category_with_no_trips_has_zero_count(self):
        CategoryFactory(name="Aerial Adventures")
        categories = self.get_categories()
        self.assertEqual(categories["Aerial Adventures"]["trips_count"], 0)

    def test_category_icon_exposed(self):
        CategoryFactory(name="Hiking & Camping", icon="mountain")
        categories = self.get_categories()
        self.assertEqual(categories["Hiking & Camping"]["icon"], "mountain")

    def test_category_icon_defaults_to_empty_string(self):
        CategoryFactory(name="No Icon Category")
        categories = self.get_categories()
        self.assertEqual(categories["No Icon Category"]["icon"], "")

    def test_inactive_category_excluded(self):
        CategoryFactory(name="Retired Category", is_active=False)
        categories = self.get_categories()
        self.assertNotIn("Retired Category", categories)

    def test_ordered_by_trips_count_descending(self):
        CategoryFactory(name="Popular")
        CategoryFactory(name="Quiet")
        TripFactory.create_batch(
            3, categories=["Popular"], is_active=True, trip_schedule=None
        )
        TripFactory(categories=["Quiet"], is_active=True, trip_schedule=None)

        response = self.client.get(self.url, {}, headers=self.headers)
        names = [item["name"] for item in response.json()["results"]]
        self.assertLess(names.index("Popular"), names.index("Quiet"))

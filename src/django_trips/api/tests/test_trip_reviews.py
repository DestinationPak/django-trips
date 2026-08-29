"""Tests for the per-trip review list endpoint (`TripReviewListView`)."""

from django.urls import reverse
from rest_framework import status

from django_trips.tests.factories import (
    AuthenticatedUserTestCase,
    LocationFactory,
    TripFactory,
    TripReviewFactory,
)


class TripReviewListAPITestCase(AuthenticatedUserTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.trip = TripFactory()
        cls.other_trip = TripFactory()

    def get_reviews_url(self, trip_id):
        return reverse("trips-api:trip-reviews", kwargs={"trip_id": trip_id})

    def test_without_authentication(self):
        """Verify the review list is public - no authentication required."""
        TripReviewFactory(trip=self.trip)
        response = self.client.get(self.get_reviews_url(self.trip.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.json()["results"]), 1)

    def test_only_returns_reviews_for_the_requested_trip(self):
        TripReviewFactory(trip=self.trip)
        TripReviewFactory(trip=self.other_trip)
        response = self.client.get(self.get_reviews_url(self.trip.id))
        results = response.json()["results"]
        self.assertEqual(len(results), 1)

    def test_excludes_unverified_reviews(self):
        """Matches the `reviews_count` scoping in get_trip_review_summary_data -
        an unverified review shouldn't show up in the public list either."""
        TripReviewFactory(trip=self.trip, is_verified=True)
        TripReviewFactory(trip=self.trip, is_verified=False)
        response = self.client.get(self.get_reviews_url(self.trip.id))
        results = response.json()["results"]
        self.assertEqual(len(results), 1)

    def test_ordered_newest_first(self):
        older = TripReviewFactory(trip=self.trip, name="Older Review")
        newer = TripReviewFactory(trip=self.trip, name="Newer Review")
        response = self.client.get(self.get_reviews_url(self.trip.id))
        names = [r["name"] for r in response.json()["results"]]
        self.assertEqual(names, [newer.name, older.name])

    def test_result_fields(self):
        location = LocationFactory(name="Lahore")
        review = TripReviewFactory(
            trip=self.trip,
            name="Sana R.",
            location=location,
            meals=5,
            accommodation=4,
            transport=5,
            value_for_money=4,
            overall=5,
            comment="Loved it.",
        )
        response = self.client.get(self.get_reviews_url(self.trip.id))
        result = response.json()["results"][0]
        self.assertEqual(result["id"], review.id)
        self.assertEqual(result["name"], "Sana R.")
        self.assertEqual(result["location"], "Lahore")
        self.assertEqual(result["meals"], 5)
        self.assertEqual(result["accommodation"], 4)
        self.assertEqual(result["transport"], 5)
        self.assertEqual(result["value_for_money"], 4)
        self.assertEqual(result["overall"], 5)
        self.assertEqual(result["comment"], "Loved it.")
        self.assertIsNotNone(result["created_at"])
        self.assertNotIn("email", result)

    def test_location_is_null_when_not_set(self):
        TripReviewFactory(trip=self.trip, location=None)
        response = self.client.get(self.get_reviews_url(self.trip.id))
        self.assertIsNone(response.json()["results"][0]["location"])

    def test_pagination_envelope(self):
        TripReviewFactory(trip=self.trip)
        response = self.client.get(self.get_reviews_url(self.trip.id))
        data = response.json()
        for key in ("next", "previous", "count", "current", "pages", "results"):
            self.assertIn(key, data)

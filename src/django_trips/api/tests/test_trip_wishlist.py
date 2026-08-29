"""Tests for the trip wishlist toggle endpoint and the is_wished field
exposed on TripListSerializer/TripDetailSerializer.
"""

from django.urls import reverse
from rest_framework import status

from django_trips.models import TripWishlist
from django_trips.tests.factories import (
    AuthenticatedUserTestCase,
    TripFactory,
    TripWishlistFactory,
    UserFactory,
)


class TripWishlistToggleAPITestCase(AuthenticatedUserTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.trip = TripFactory(trip_schedule=None)

    def get_wishlist_url(self, identifier):
        return reverse(
            "trips-api:trip-wishlist", kwargs={"identifier": identifier}
        )

    def test_toggle_requires_authentication(self):
        response = self.client.post(self.get_wishlist_url(self.trip.slug))
        # SessionAuthentication (first in authentication_classes) doesn't set
        # WWW-Authenticate, so DRF falls back to 403 rather than 401 here -
        # see TripDeletePermissionTests.test_delete_unauthenticated.
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_toggle_adds_to_wishlist(self):
        response = self.client.post(
            self.get_wishlist_url(self.trip.slug), headers=self.headers
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json(), {"is_wished": True})
        self.assertTrue(
            TripWishlist.objects.filter(user=self.user, trip=self.trip).exists()
        )

    def test_toggle_removes_from_wishlist(self):
        TripWishlistFactory(user=self.user, trip=self.trip)
        response = self.client.post(
            self.get_wishlist_url(self.trip.slug), headers=self.headers
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json(), {"is_wished": False})
        self.assertFalse(
            TripWishlist.objects.filter(user=self.user, trip=self.trip).exists()
        )

    def test_toggle_twice_is_idempotent_back_to_original_state(self):
        url = self.get_wishlist_url(self.trip.slug)
        self.client.post(url, headers=self.headers)
        self.client.post(url, headers=self.headers)
        self.assertFalse(
            TripWishlist.objects.filter(user=self.user, trip=self.trip).exists()
        )

    def test_toggle_by_id(self):
        response = self.client.post(
            self.get_wishlist_url(self.trip.id), headers=self.headers
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json(), {"is_wished": True})

    def test_toggle_nonexistent_trip_returns_404(self):
        response = self.client.post(
            self.get_wishlist_url("non-existent-slug"), headers=self.headers
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_wishlisting_is_scoped_per_user(self):
        """One user's wishlist toggle shouldn't affect another user's."""
        other_user = UserFactory()
        TripWishlistFactory(user=other_user, trip=self.trip)

        response = self.client.post(
            self.get_wishlist_url(self.trip.slug), headers=self.headers
        )
        self.assertEqual(response.json(), {"is_wished": True})
        self.assertTrue(
            TripWishlist.objects.filter(user=other_user, trip=self.trip).exists()
        )
        self.assertTrue(
            TripWishlist.objects.filter(user=self.user, trip=self.trip).exists()
        )


class TripIsWishedFieldAPITestCase(AuthenticatedUserTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.trip = TripFactory(trip_schedule=None)

    def get_detail(self, identifier=None, headers=None):
        url = reverse(
            "trips-api:trip-detail",
            kwargs={"identifier": identifier or self.trip.slug},
        )
        response = self.client.get(url, headers=self.headers if headers is None else headers)
        return response.json()

    def get_list_item(self, headers=None):
        url = reverse("trips-api:trip-list")
        response = self.client.get(
            url, headers=self.headers if headers is None else headers
        )
        return response.json()["results"][0]

    def test_is_wished_false_by_default_on_detail(self):
        self.assertFalse(self.get_detail()["is_wished"])

    def test_is_wished_true_after_wishlisting_on_detail(self):
        TripWishlistFactory(user=self.user, trip=self.trip)
        self.assertTrue(self.get_detail()["is_wished"])

    def test_is_wished_false_for_other_users_wishlist(self):
        other_user = UserFactory()
        TripWishlistFactory(user=other_user, trip=self.trip)
        self.assertFalse(self.get_detail()["is_wished"])

    def test_is_wished_false_for_anonymous_user(self):
        self.assertFalse(self.get_detail(headers={})["is_wished"])

    def test_is_wished_true_on_list_endpoint(self):
        TripWishlistFactory(user=self.user, trip=self.trip)
        self.assertTrue(self.get_list_item()["is_wished"])

    def test_is_wished_false_on_list_endpoint_when_not_wishlisted(self):
        self.assertFalse(self.get_list_item()["is_wished"])

"""TripViewSet is the public catalog (surface B) - read-only, no exceptions.

Trip management (create/update/delete) moved out of the lib entirely; it lives in
destipak's tenancy-aware operator API, built against TripCreateSerializer imported
directly from django_trips.api.serializers. These tests lock in that the public
endpoint itself never regains a write method - not "unauthorized", flatly absent.
"""

from django.urls import reverse

from django_trips.tests.factories import AuthenticatedUserTestCase, TripFactory


class TripWriteMethodsDisabledTests(AuthenticatedUserTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.trip = TripFactory()
        cls.list_url = reverse("trips-api:trip-list")
        cls.detail_url = reverse(
            "trips-api:trip-detail", kwargs={"identifier": cls.trip.slug}
        )

    def test_create_not_allowed(self):
        response = self.client.post(self.list_url, {}, headers=self.headers)
        self.assertEqual(response.status_code, 405)

    def test_update_not_allowed(self):
        response = self.client.put(self.detail_url, {}, headers=self.headers)
        self.assertEqual(response.status_code, 405)

    def test_delete_not_allowed(self):
        response = self.client.delete(self.detail_url, headers=self.headers)
        self.assertEqual(response.status_code, 405)

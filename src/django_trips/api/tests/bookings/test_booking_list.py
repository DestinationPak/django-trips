from datetime import timedelta
from unittest import mock

import ddt
from django.urls import reverse
from django.utils import timezone
from rest_framework_simplejwt.tokens import AccessToken

from django_trips.choices import BookingStatus, ScheduleStatus
from django_trips.models import TripBooking
from django_trips.tests.factories import (AuthenticatedUserTestCase,
                                          TripBookingFactory, TripFactory,
                                          TripScheduleFactory, UserFactory)


class TripBookingListTestCase(AuthenticatedUserTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.user.is_staff = True
        cls.user.save()

        cls.trip = TripFactory.create(
            locations=["Lahore", "Gilgit"],
            facilities=["Transport", "Food"],
            gear=["Backpack", "Glasses"],
            categories=["Outdoors", "Hiking"],
        )
        cls.schedule1 = TripScheduleFactory(
            trip=cls.trip, start_date=timezone.now().date() + timedelta(days=7)
        )
        cls.schedule2 = TripScheduleFactory(
            trip=cls.trip, start_date=timezone.now() + timedelta(days=20)
        )

        TripBookingFactory(
            schedule=cls.schedule1,
            full_name="Ali Raza",
            phone_number="03001234567",
            number="DPT00123AA",
            adults=5,
        )
        TripBookingFactory(
            schedule=cls.schedule2,
            full_name="Sara Khan",
            phone_number="03111234567",
            number="DPT00124BB",
            adults=10,
        )

        cls.url = reverse("trips-api:trip-bookings", kwargs={"trip_id": cls.trip.pk})

    def make_api_call(self, params):
        response = self.client.get(
            self.url, params, headers=self.headers, content_type="application/json"
        )
        self.assertEqual(response.status_code, 200, response.json())
        return response.json()

    def test_list_bookings_unauthenticated_user(self):
        response = self.client.get(self.url, {}, content_type="application/json")
        self.assertEqual(response.status_code, 403, response.json())
        self.assertEqual(
            response.json(), {"detail": "Authentication credentials were not provided."}
        )

    def test_list_bookings_regular_user(self):
        user = UserFactory()
        access_token = AccessToken.for_user(user)
        headers = {"Authorization": f"Bearer {access_token}"}
        response = self.client.get(self.url, {}, headers=headers)
        self.assertEqual(response.status_code, 403, response.json())
        self.assertEqual(
            response.json(),
            {"detail": "You do not have permission to perform this action."},
        )

    def test_list_bookings(self):
        data = self.make_api_call({})
        self.assertEqual(len(data["results"]), 2)

    def test_search_booking_by_name(self):
        data = self.make_api_call({"search": "Sara"})
        self.assertEqual(len(data["results"]), 1)
        self.assertEqual(data["results"][0]["full_name"], "Sara Khan")

    def test_filter_by_schedule(self):
        data = self.make_api_call({"schedule": self.schedule1.id})
        self.assertEqual(len(data["results"]), 1)

    def test_order_by_target_date_desc(self):
        data = self.make_api_call({"ordering": "-target_date"})
        dates = [item["target_date"] for item in data["results"]]
        self.assertTrue(dates == sorted(dates, reverse=True))

    def test_order_by_full_name(self):
        data = self.make_api_call({"ordering": "full_name"})
        names = [item["full_name"] for item in data["results"]]
        self.assertEqual(names, sorted(names))

        data = self.make_api_call({"ordering": "-full_name"})
        names = [item["full_name"] for item in data["results"]]
        self.assertEqual(names, sorted(names, reverse=True))

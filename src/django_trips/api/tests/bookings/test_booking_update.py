from datetime import timedelta
from unittest import mock

from django.urls import reverse
from django.utils import timezone

from django_trips.models import TripBooking
from django_trips.tests.factories import (AuthenticatedUserTestCase,
                                          TripBookingFactory, TripFactory,
                                          TripScheduleFactory)


class BookingUpdateTests(AuthenticatedUserTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.trip = TripFactory()
        cls.schedule_date = timezone.now().date() + timedelta(days=7)
        cls.trip_schedule = TripScheduleFactory(
            trip=cls.trip, start_date=cls.schedule_date
        )
        cls.trip_schedule2 = TripScheduleFactory(
            trip=cls.trip, start_date=cls.schedule_date
        )
        cls.booking = TripBookingFactory(
            schedule=cls.trip_schedule,
            full_name="Ali Raza",
            phone_number="03001234567",
            number="DPT00123AA",
            target_date=cls.schedule_date,
            adults=5,
            message="booking 1",
            created_by=cls.user,
        )
        cls.other_users_booking = TripBookingFactory(
            schedule=cls.trip_schedule,
            number="DPT00125CC",
            target_date=cls.schedule_date,
        )

        cls.url = reverse(
            "trips-api:booking-detail", kwargs={"number": cls.booking.number}
        )
        cls.other_users_booking_url = reverse(
            "trips-api:booking-detail",
            kwargs={"number": cls.other_users_booking.number},
        )

    def test_update_other_users_booking_returns_404(self):
        """A booking must only be updatable by the user who created it (IDOR regression)."""
        payload = {
            "full_name": "Hijacked Name",
            "email": "hijacked@example.com",
            "phone_number": "+923000000000",
            "adults": 1,
            "target_date": self.other_users_booking.target_date.isoformat(),
            "schedule": self.trip_schedule.pk,
        }
        response = self.client.put(
            self.other_users_booking_url,
            payload,
            headers=self.headers,
            content_type="application/json",
        )
        assert response.status_code == 404

    def test_update_trip_booking(self):
        payload = {
            "full_name": "Updated Name",
            "email": "updated@example.com",
            "phone_number": "+923000000000",
            "adults": 2,
            "target_date": self.booking.target_date.isoformat(),
            "schedule": self.trip_schedule2.pk,
            "created_by": 99,
        }

        response = self.client.put(
            self.url, payload, headers=self.headers, content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertEqual(data["full_name"], "Updated Name")
        self.assertEqual(data["email"], "updated@example.com")
        self.assertEqual(data["phone_number"], "+923000000000")
        self.assertEqual(data["adults"], 2)

        self.assertEqual(data["schedule_details"]["id"], self.trip_schedule.pk)
        self.assertEqual(data["created_by"], self.user.id)

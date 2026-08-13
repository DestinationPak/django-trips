from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from django_trips.choices import BookingStatus
from django_trips.tests.factories import TripBookingFactory, TripFactory, TripScheduleFactory


class TripBookingLookupTestCase(TestCase):
    maxDiff = None

    @classmethod
    def setUpTestData(cls):
        cls.trip = TripFactory()
        cls.schedule_date = timezone.now().date() + timedelta(days=7)
        cls.trip_schedule = TripScheduleFactory(
            trip=cls.trip, start_date=cls.schedule_date
        )
        cls.booking = TripBookingFactory(
            schedule=cls.trip_schedule,
            full_name="Ali Raza",
            email="ali@example.com",
            number="DPT00123AA",
            otp="4242",
            target_date=cls.schedule_date,
            created_by=None,
        )
        cls.url = reverse("trips-api:trip-bookings-lookup")

    def test_lookup_by_number_and_email(self):
        response = self.client.get(
            self.url, {"number": self.booking.number, "email": "ali@example.com"}
        )
        self.assertEqual(response.status_code, 200, response.json())
        self.assertEqual(response.json()["number"], self.booking.number)

    def test_lookup_is_case_insensitive_on_email(self):
        response = self.client.get(
            self.url, {"number": self.booking.number, "email": "ALI@EXAMPLE.COM"}
        )
        self.assertEqual(response.status_code, 200, response.json())

    def test_lookup_rejects_mismatched_email(self):
        response = self.client.get(
            self.url,
            {"number": self.booking.number, "email": "someone-else@example.com"},
        )
        self.assertEqual(response.status_code, 404)

    def test_lookup_by_number_and_otp(self):
        response = self.client.get(
            self.url, {"number": self.booking.number, "otp": "4242"}
        )
        self.assertEqual(response.status_code, 200, response.json())
        self.assertEqual(response.json()["number"], self.booking.number)

    def test_lookup_rejects_mismatched_otp(self):
        response = self.client.get(
            self.url, {"number": self.booking.number, "otp": "0000"}
        )
        self.assertEqual(response.status_code, 404)

    def test_lookup_response_does_not_expose_otp(self):
        response = self.client.get(
            self.url, {"number": self.booking.number, "otp": "4242"}
        )
        self.assertNotIn("otp", response.json())

    def test_lookup_returns_status_history(self):
        self.booking.set_status(BookingStatus.CONFIRMED, reason="advance payment received")

        response = self.client.get(
            self.url, {"number": self.booking.number, "otp": "4242"}
        )

        events = response.json()["status_events"]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["old_status"], BookingStatus.PENDING)
        self.assertEqual(events[0]["new_status"], BookingStatus.CONFIRMED)
        self.assertEqual(events[0]["reason"], "advance payment received")

    def test_lookup_status_history_hides_the_staff_actor(self):
        self.booking.set_status(BookingStatus.CONFIRMED)

        response = self.client.get(
            self.url, {"number": self.booking.number, "otp": "4242"}
        )

        self.assertNotIn("changed_by", response.json()["status_events"][0])

    def test_lookup_requires_number_and_one_of_otp_or_email(self):
        response = self.client.get(self.url, {"number": self.booking.number})
        self.assertEqual(response.status_code, 400)

        response = self.client.get(self.url, {"email": "ali@example.com"})
        self.assertEqual(response.status_code, 400)

        response = self.client.get(self.url, {"otp": "4242"})
        self.assertEqual(response.status_code, 400)

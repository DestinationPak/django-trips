from datetime import timedelta
from unittest import mock

import ddt
from django.urls import reverse
from django.utils import timezone

from django_trips.choices import BookingStatus
from django_trips.models import TripBooking
from django_trips.tests.factories import (AuthenticatedUserTestCase,
                                          TripBookingFactory, TripFactory,
                                          TripScheduleFactory)


@ddt.ddt
class TripBookingCancelTests(AuthenticatedUserTestCase):

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

    def setUp(self):
        super().setUp()
        self.booking = TripBookingFactory(
            schedule=self.trip_schedule,
            full_name="Ali Raza",
            phone_number="03001234567",
            number="DPT00123AA",
            target_date=self.schedule_date,
            adults=5,
            message="booking 1",
            created_by=self.user,
        )
        self.url = reverse("trips-api:booking-cancel", args=[self.booking.number])

        self.other_users_booking = TripBookingFactory(
            schedule=self.trip_schedule,
            number="DPT00126DD",
            target_date=self.schedule_date,
        )
        self.other_users_booking_url = reverse(
            "trips-api:booking-cancel", args=[self.other_users_booking.number]
        )

    def test_cancel_other_users_booking_returns_404(self):
        """A booking must only be cancellable by the user who created it (IDOR regression)."""
        response = self.client.post(
            self.other_users_booking_url,
            headers=self.headers,
            content_type="application/json",
        )
        assert response.status_code == 404

    def cancel_trip_booking(self):
        response = self.client.post(
            self.url, headers=self.headers, content_type="application/json"
        )
        assert response.status_code == 200
        return response.json()

    def test_duplicate_cancel_booking(self):
        self.booking.cancel()
        response = self.client.post(
            self.url, headers=self.headers, content_type="application/json"
        )

        assert response.status_code == 400
        assert response.json() == {"detail": "Booking is already cancelled"}

    @ddt.data(
        BookingStatus.CONFIRMED,
        BookingStatus.COMPLETED,
        BookingStatus.PARTIAL_PAYMENT,
    )
    def test_cancel_booking_not_allowed(self, status):
        self.booking.status = status
        self.booking.save()

        response = self.client.post(
            self.url, headers=self.headers, content_type="application/json"
        )
        assert response.status_code == 400
        assert response.json() == {
            "detail": "Automatic cancellation not allowed at this time."
        }

    @ddt.data(BookingStatus.PENDING, BookingStatus.WAITING_PAYMENT)
    def test_cancel_booking_success(self, status):
        self.booking.status = status
        self.booking.save()

        data = self.cancel_trip_booking()
        assert data["status"] == "CANCELLED"
        assert "otp" not in data

        self.booking.refresh_from_db()
        assert self.booking.status == "CANCELLED"
        assert self.booking.cancelled_at is not None

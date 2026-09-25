from datetime import timedelta
from unittest.mock import MagicMock

from django.contrib import admin
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from django_trips.admin import REOPEN_NOT_ALLOWED, TripAdmin, deactivate_hosts
from django_trips.choices import BookingStatus
from django_trips.models import BookingStatusEvent, Host, Trip, TripAvailability, TripBooking
from django_trips.tests.factories import (
    HostFactory,
    TripBookingFactory,
    TripFactory,
    TripScheduleFactory,
    UserFactory,
)


class DeactivateHostsActionTestCase(TestCase):
    """Verify the HostAdmin `deactivate_hosts` action cascades to trips."""

    @classmethod
    def setUpTestData(cls):
        cls.host = HostFactory(is_active=True)
        cls.other_host = HostFactory(is_active=True)
        cls.trip1 = TripFactory(host=cls.host, is_active=True)
        cls.trip2 = TripFactory(host=cls.host, is_active=True)
        cls.other_trip = TripFactory(host=cls.other_host, is_active=True)

    def test_deactivates_selected_host(self):
        deactivate_hosts(MagicMock(), None, Host.objects.filter(pk=self.host.pk))
        self.host.refresh_from_db()
        self.assertFalse(self.host.is_active)

    def test_deactivates_all_trips_of_selected_host(self):
        deactivate_hosts(MagicMock(), None, Host.objects.filter(pk=self.host.pk))
        self.trip1.refresh_from_db()
        self.trip2.refresh_from_db()
        self.assertFalse(self.trip1.is_active)
        self.assertFalse(self.trip2.is_active)

    def test_does_not_affect_other_hosts_or_their_trips(self):
        deactivate_hosts(MagicMock(), None, Host.objects.filter(pk=self.host.pk))
        self.other_host.refresh_from_db()
        self.other_trip.refresh_from_db()
        self.assertTrue(self.other_host.is_active)
        self.assertTrue(self.other_trip.is_active)

    def test_host_with_no_trips_does_not_error(self):
        lone_host = HostFactory(is_active=True)
        deactivate_hosts(MagicMock(), None, Host.objects.filter(pk=lone_host.pk))
        lone_host.refresh_from_db()
        self.assertFalse(lone_host.is_active)

    def test_message_user_reports_host_and_trip_counts(self):
        modeladmin = MagicMock()
        deactivate_hosts(modeladmin, None, Host.objects.filter(pk=self.host.pk))
        message = modeladmin.message_user.call_args[0][1]
        self.assertIn("1 host", message)
        self.assertIn("2", message)


class TripAdminGetDateTestCase(TestCase):
    """TripAdmin.get_date() feeds the 'Availability Up to' admin list column."""

    def test_returns_end_dates_of_all_availabilities(self):
        trip = TripFactory(trip_schedule=None)
        first_end_date = (timezone.now() + timedelta(days=5)).date()
        second_end_date = (timezone.now() + timedelta(days=10)).date()
        TripAvailability.objects.create(trip=trip, end_date=first_end_date)
        TripAvailability.objects.create(trip=trip, end_date=second_end_date)

        modeladmin = TripAdmin(Trip, admin.site)

        self.assertEqual(
            modeladmin.get_date(trip), [first_end_date, second_end_date]
        )

    def test_returns_empty_list_without_availabilities(self):
        trip = TripFactory(trip_schedule=None)
        modeladmin = TripAdmin(Trip, admin.site)
        self.assertEqual(modeladmin.get_date(trip), [])


def admin_form_data(form):
    """The POST data a browser would send for an unchanged admin form."""
    data = {}
    for name in form.fields:
        bound = form[name]
        value = bound.value()
        widget = bound.field.widget
        if hasattr(widget, "widgets") and hasattr(widget, "decompress"):
            parts = value if isinstance(value, (list, tuple)) else widget.decompress(value)
            for index, part in enumerate(parts):
                data[f"{name}_{index}"] = "" if part is None else part
        elif isinstance(value, bool):
            if value:
                data[name] = "on"
        elif isinstance(value, (list, tuple)):
            data[name] = [str(item) for item in value]
        else:
            data[name] = "" if value is None else value
    return data


class TripBookingAdminTestCase(TestCase):
    """Cancelling, reopening and deleting a booking in the admin keep seats in step."""

    def setUp(self):
        super().setUp()
        self.client.force_login(
            UserFactory(is_staff=True, is_superuser=True, email="staff@example.com")
        )
        self.schedule = TripScheduleFactory(available_seats=20, booked_seats=10)
        self.booking = TripBookingFactory(
            schedule=self.schedule, adults=2, children=1, status=BookingStatus.CONFIRMED
        )
        self.change_url = reverse("admin:django_trips_tripbooking_change", args=[self.booking.pk])

    def post_status(self, status):
        form = self.client.get(self.change_url).context["adminform"].form
        return self.client.post(self.change_url, {**admin_form_data(form), "status": status})

    def booked_seats(self):
        self.schedule.refresh_from_db()
        return self.schedule.booked_seats

    def test_cancelling_gives_the_seats_back_and_records_who(self):
        response = self.post_status(BookingStatus.CANCELLED)

        self.assertEqual(response.status_code, 302)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, BookingStatus.CANCELLED)
        self.assertIsNotNone(self.booking.cancelled_at)
        self.assertEqual(self.booked_seats(), 7)
        event = BookingStatusEvent.objects.filter(booking=self.booking).latest("pk")
        self.assertEqual(event.changed_by.email, "staff@example.com")

    def test_saving_without_a_status_change_leaves_seats_alone(self):
        response = self.post_status(BookingStatus.CONFIRMED)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.booked_seats(), 10)

    def test_a_cancelled_booking_cannot_be_reopened(self):
        self.post_status(BookingStatus.CANCELLED)

        response = self.post_status(BookingStatus.PENDING)

        self.assertEqual(response.status_code, 200)
        self.assertIn(REOPEN_NOT_ALLOWED, response.context["adminform"].form.errors["status"])
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, BookingStatus.CANCELLED)
        self.assertEqual(self.booked_seats(), 7)

    def test_seat_fields_are_read_only_once_the_booking_exists(self):
        form = self.client.get(self.change_url).context["adminform"].form

        for name in ("schedule", "adults", "children"):
            self.assertNotIn(name, form.fields)

    def test_deleting_a_live_booking_gives_the_seats_back(self):
        delete_url = reverse("admin:django_trips_tripbooking_delete", args=[self.booking.pk])

        response = self.client.post(delete_url, {"post": "yes"})

        self.assertEqual(response.status_code, 302)
        self.assertFalse(TripBooking.objects.filter(pk=self.booking.pk).exists())
        self.assertEqual(self.booked_seats(), 7)

    def test_deleting_a_cancelled_booking_does_not_give_seats_back_twice(self):
        self.post_status(BookingStatus.CANCELLED)
        delete_url = reverse("admin:django_trips_tripbooking_delete", args=[self.booking.pk])

        self.client.post(delete_url, {"post": "yes"})

        self.assertEqual(self.booked_seats(), 7)

    def test_bulk_delete_gives_every_bookings_seats_back(self):
        other = TripBookingFactory(schedule=self.schedule, adults=1, children=0, status=BookingStatus.PENDING)
        changelist_url = reverse("admin:django_trips_tripbooking_changelist")

        self.client.post(
            changelist_url,
            {"action": "delete_selected", "_selected_action": [self.booking.pk, other.pk], "post": "yes"},
        )

        self.assertFalse(TripBooking.objects.filter(pk__in=[self.booking.pk, other.pk]).exists())
        self.assertEqual(self.booked_seats(), 6)

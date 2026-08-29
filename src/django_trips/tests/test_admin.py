from datetime import timedelta
from unittest.mock import MagicMock

from django.contrib import admin
from django.test import TestCase
from django.utils import timezone

from django_trips.admin import TripAdmin, deactivate_hosts
from django_trips.models import Host, Trip, TripAvailability
from django_trips.tests.factories import HostFactory, TripFactory


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

from datetime import timedelta

from django.test import TestCase

from django_trips.utils import format_trip_duration


class FormatTripDurationTestCase(TestCase):
    def test_none_duration_returns_none(self):
        self.assertIsNone(format_trip_duration(None))

    def test_zero_days_returns_none(self):
        self.assertIsNone(format_trip_duration(timedelta(days=0)))

    def test_negative_days_returns_none(self):
        self.assertIsNone(format_trip_duration(timedelta(days=-1)))

    def test_single_day_has_no_nights(self):
        self.assertEqual(format_trip_duration(timedelta(days=1)), "1 Day")

    def test_two_days_has_singular_night(self):
        self.assertEqual(format_trip_duration(timedelta(days=2)), "2 Days 1 Night")

    def test_multiple_days_has_plural_nights(self):
        self.assertEqual(format_trip_duration(timedelta(days=7)), "7 Days 6 Nights")

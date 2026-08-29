from django.test import TestCase

from django_trips.api.filters import TimedeltaFromDaysFilter
from django_trips.models import TripSchedule


class TimedeltaFromDaysFilterTestCase(TestCase):
    """TimedeltaFromDaysFilter converts a "days" query value to a timedelta;
    an unparseable value should yield an empty queryset rather than raise."""

    def test_invalid_value_returns_empty_queryset(self):
        duration_filter = TimedeltaFromDaysFilter(field_name="duration")
        result = duration_filter.filter(TripSchedule.objects.all(), "not-a-number")
        self.assertEqual(result.count(), 0)

    def test_none_value_is_a_noop(self):
        duration_filter = TimedeltaFromDaysFilter(field_name="duration")
        result = duration_filter.filter(TripSchedule.objects.all(), None)
        self.assertEqual(result.count(), TripSchedule.objects.count())

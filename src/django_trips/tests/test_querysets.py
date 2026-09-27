from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.test import TestCase, override_settings
from django.utils.timezone import localdate, now

from django_trips.choices import BookingStatus, LocationType, ScheduleStatus
from django_trips.locations import (
    destinations_with_trip_counts,
    expand_destination_slugs,
    trips_booked_to,
)
from django_trips.models import Category, Host, Trip, TripBooking, TripReview, TripSchedule
from django_trips.tests.factories import (
    CategoryFactory,
    HostFactory,
    LocationFactory,
    TripBookingFactory,
    TripFactory,
    TripPackageFactory,
    TripReviewFactory,
    TripScheduleFactory,
)


class WithTripCountsTestCase(TestCase):
    def test_counts_only_active_trips_busiest_first(self):
        quiet = CategoryFactory(name="Quiet")
        busy = CategoryFactory(name="Busy")
        TripFactory(categories=[busy], trip_schedule=None)
        TripFactory(categories=[busy], trip_schedule=None)
        TripFactory(categories=[quiet], trip_schedule=None)
        TripFactory(categories=[quiet], is_active=False, trip_schedule=None)

        counts = [
            (category.name, category.trips_count)
            for category in Category.objects.filter(pk__in=[quiet.pk, busy.pk]).with_trip_counts()
        ]

        self.assertEqual(counts, [("Busy", 2), ("Quiet", 1)])

    def test_hosts_have_trip_counts_too(self):
        host = HostFactory()
        TripFactory(host=host, trip_schedule=None)

        self.assertEqual(Host.objects.filter(pk=host.pk).with_trip_counts().get().trips_count, 1)


class TripWithPriceTestCase(TestCase):
    def test_price_is_the_cheapest_package(self):
        trip = TripFactory(trip_schedule=None)
        trip.packages.update(base_price=9000)
        TripPackageFactory(trip=trip, base_price=5000)

        self.assertEqual(Trip.objects.filter(pk=trip.pk).with_price().get().price, 5000)

    def test_keeps_the_default_ordering(self):
        self.assertEqual(
            Trip.objects.with_price().query.order_by,
            tuple(Trip._meta.ordering),  # pylint:disable=protected-access
        )


class TripScheduleWithPriceTestCase(TestCase):
    def test_price_is_the_cheapest_package_plus_the_date_surcharge(self):
        trip = TripFactory(trip_schedule=None)
        trip.packages.update(base_price=5000)
        schedule = TripScheduleFactory(trip=trip, additional_price=700)

        self.assertEqual(
            TripSchedule.objects.filter(pk=schedule.pk).with_price().get().price, 5700
        )


class ExpandDestinationSlugsTestCase(TestCase):
    def test_a_region_expands_to_its_children(self):
        region = LocationFactory(name="Galiyat", type=LocationType.REGION)
        LocationFactory(name="Nathia Gali", type=LocationType.CITY, parent=region)

        self.assertEqual(
            expand_destination_slugs(["galiyat"]), {"galiyat", "nathia-gali"}
        )

    def test_a_city_does_not_expand(self):
        city = LocationFactory(name="Skardu", type=LocationType.CITY)
        LocationFactory(name="Shangrila", type=LocationType.CITY, parent=city)

        self.assertEqual(expand_destination_slugs(["skardu"]), {"skardu"})


class DestinationsWithTripCountsTestCase(TestCase):
    def test_a_region_counts_its_childrens_trips(self):
        region = LocationFactory(name="Galiyat", type=LocationType.REGION)
        town = LocationFactory(name="Nathia Gali", type=LocationType.CITY, parent=region)
        TripFactory(destination=town, trip_schedule=None)

        counts = {
            location.name: location.trips_count
            for location in destinations_with_trip_counts()
        }

        self.assertEqual(counts, {"Galiyat": 1, "Nathia Gali": 1})

    def test_leaves_out_locations_without_trips(self):
        LocationFactory(name="Empty")

        self.assertFalse(destinations_with_trip_counts().filter(name="Empty").exists())


class TripScheduleBookableTestCase(TestCase):
    def test_only_upcoming_published_departures_soonest_first(self):
        trip = TripFactory(trip_schedule=None)
        later = TripScheduleFactory(trip=trip, status=ScheduleStatus.PUBLISHED, start_date=now() + timedelta(days=20))
        sooner = TripScheduleFactory(trip=trip, status=ScheduleStatus.PUBLISHED, start_date=now() + timedelta(days=5))
        TripScheduleFactory(trip=trip, status=ScheduleStatus.DRAFT, start_date=now() + timedelta(days=6))
        TripScheduleFactory(trip=trip, status=ScheduleStatus.PUBLISHED, start_date=now() - timedelta(days=1))

        self.assertEqual(list(trip.schedules.bookable()), [sooner, later])


class TripReviewVerifiedTestCase(TestCase):
    def test_leaves_out_unverified_reviews(self):
        trip = TripFactory(trip_schedule=None)
        verified = TripReviewFactory(trip=trip, is_verified=True)
        TripReviewFactory(trip=trip, is_verified=False)

        self.assertEqual(list(TripReview.objects.verified()), [verified])


class TripBookingMatchingGuestTestCase(TestCase):
    def setUp(self):
        super().setUp()
        self.booking = TripBookingFactory(email="guest@example.com")

    def test_matches_number_and_otp(self):
        matches = TripBooking.objects.matching_guest(self.booking.number, otp=self.booking.otp)

        self.assertEqual(list(matches), [self.booking])

    def test_matches_number_and_email_ignoring_case(self):
        matches = TripBooking.objects.matching_guest(self.booking.number, email="GUEST@example.com")

        self.assertEqual(list(matches), [self.booking])

    def test_never_matches_on_number_alone(self):
        self.assertFalse(TripBooking.objects.matching_guest(self.booking.number).exists())

    def test_a_wrong_second_factor_matches_nothing(self):
        matches = TripBooking.objects.matching_guest(self.booking.number, email="someone@else.com")

        self.assertFalse(matches.exists())


class TripsBookedToTestCase(TestCase):
    def test_a_region_includes_its_childrens_trips(self):
        region = LocationFactory(name="Galiyat", type=LocationType.REGION)
        town = LocationFactory(name="Nathia Gali", type=LocationType.CITY, parent=region)
        own = TripFactory(destination=region, trip_schedule=None)
        child = TripFactory(destination=town, trip_schedule=None)

        self.assertEqual(set(trips_booked_to(region)), {own, child})

    def test_a_city_only_includes_its_own_trips(self):
        city = LocationFactory(name="Skardu", type=LocationType.CITY)
        village = LocationFactory(name="Shangrila", type=LocationType.CITY, parent=city)
        own = TripFactory(destination=city, trip_schedule=None)
        TripFactory(destination=village, trip_schedule=None)

        self.assertEqual(list(trips_booked_to(city)), [own])


class TripBookingStateTestCase(TestCase):
    """Sorting a traveler's bookings into upcoming, past and cancelled."""

    def booking(
        self, *, start_date=None, end_date=None, target_date=None, status=BookingStatus.PENDING, **fields
    ):
        schedule = TripScheduleFactory(
            status=ScheduleStatus.PUBLISHED, start_date=start_date, end_date=end_date
        )
        return TripBookingFactory(schedule=schedule, target_date=target_date, status=status, **fields)

    def test_upcoming_is_today_or_later_soonest_first(self):
        today = localdate()
        later = self.booking(start_date=today + timedelta(days=9))
        soon = self.booking(start_date=today)
        self.booking(start_date=today - timedelta(days=1))

        self.assertEqual(list(TripBooking.objects.upcoming()), [soon, later])

    def test_past_is_before_today_latest_first(self):
        today = localdate()
        older = self.booking(start_date=today - timedelta(days=30))
        recent = self.booking(start_date=today - timedelta(days=1))
        self.booking(start_date=today)

        self.assertEqual(list(TripBooking.objects.past()), [recent, older])

    def test_a_trip_under_way_is_upcoming(self):
        today = localdate()
        under_way = self.booking(
            start_date=today - timedelta(days=1), end_date=today + timedelta(days=3)
        )
        ends_today = self.booking(start_date=today - timedelta(days=4), end_date=today)

        self.assertEqual(list(TripBooking.objects.upcoming()), [ends_today, under_way])
        self.assertFalse(TripBooking.objects.past().exists())

    def test_a_trip_that_ended_yesterday_is_past(self):
        today = localdate()
        ended = self.booking(
            start_date=today - timedelta(days=5), end_date=today - timedelta(days=1)
        )

        self.assertEqual(list(TripBooking.objects.past()), [ended])
        self.assertEqual(TripBooking.objects.past().get().trip_end_day, today - timedelta(days=1))

    def test_only_the_dates_decide_upcoming_or_past(self):
        today = localdate()
        stale = self.booking(start_date=today - timedelta(days=3))
        completed = self.booking(
            start_date=today - timedelta(days=2), status=BookingStatus.COMPLETED
        )
        confirmed = self.booking(
            start_date=today + timedelta(days=2), status=BookingStatus.CONFIRMED
        )

        self.assertEqual(list(TripBooking.objects.past()), [completed, stale])
        self.assertEqual(list(TripBooking.objects.upcoming()), [confirmed])

    @override_settings(TIME_ZONE="America/Chicago")
    def test_target_date_uses_the_local_day(self):
        yesterday = localdate() - timedelta(days=1)
        chicago = ZoneInfo("America/Chicago")
        late_yesterday = datetime.combine(yesterday, time(20, 0), tzinfo=chicago)
        booking = self.booking(start_date=None, target_date=late_yesterday)

        self.assertEqual(late_yesterday.astimezone(UTC).date(), localdate())
        self.assertEqual(list(TripBooking.objects.past()), [booking])
        self.assertEqual(TripBooking.objects.past().get().trip_day, yesterday)

    def test_target_date_stands_in_when_the_schedule_has_no_date(self):
        yesterday = now() - timedelta(days=1)
        booking = self.booking(start_date=None, target_date=yesterday)

        self.assertEqual(list(TripBooking.objects.past()), [booking])
        self.assertFalse(TripBooking.objects.upcoming().exists())

    def test_a_booking_with_no_day_is_upcoming_and_listed_last(self):
        undated = self.booking(start_date=None, target_date=None)
        dated = self.booking(start_date=localdate() + timedelta(days=3))

        self.assertEqual(list(TripBooking.objects.upcoming()), [dated, undated])
        self.assertFalse(TripBooking.objects.past().exists())

    def test_cancelled_bookings_are_only_in_cancelled(self):
        today = localdate()
        future = self.booking(start_date=today + timedelta(days=5), status=BookingStatus.CANCELLED)
        gone = self.booking(
            start_date=today - timedelta(days=5),
            status=BookingStatus.CANCELLED,
            cancelled_at=now(),
        )

        self.assertFalse(TripBooking.objects.upcoming().exists())
        self.assertFalse(TripBooking.objects.past().exists())
        self.assertEqual(list(TripBooking.objects.cancelled()), [gone, future])

    def test_trip_day_is_annotated(self):
        day = localdate() + timedelta(days=4)
        self.booking(start_date=day)

        self.assertEqual(TripBooking.objects.upcoming().get().trip_day, day)

    def test_state_counts_match_the_lists(self):
        today = localdate()
        self.booking(start_date=today)
        self.booking(start_date=None, target_date=None)
        self.booking(start_date=today - timedelta(days=2))
        self.booking(start_date=today + timedelta(days=2), status=BookingStatus.CANCELLED)

        with self.assertNumQueries(1):
            counts = TripBooking.objects.state_counts()

        self.assertEqual(counts, {"upcoming": 2, "past": 1, "cancelled": 1})

    def test_state_counts_respect_an_earlier_filter(self):
        mine = self.booking(start_date=localdate())
        self.booking(start_date=localdate())

        counts = TripBooking.objects.filter(created_by=mine.created_by).state_counts()

        self.assertEqual(counts, {"upcoming": 1, "past": 0, "cancelled": 0})

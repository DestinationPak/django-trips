from datetime import timedelta

from django.test import TestCase
from django.utils.timezone import now

from django_trips.choices import LocationType, ScheduleStatus
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

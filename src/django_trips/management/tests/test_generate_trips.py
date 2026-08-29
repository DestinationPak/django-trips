"""Test management command"""
from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.test import TestCase
from django.utils import timezone
from django.utils.text import slugify

from django_trips.choices import PackageTier, ScheduleStatus
from django_trips.management.commands.generate_trips import (
    DEFAULT_SETTINGS,
    Command,
)
from django_trips.models import (
    Location,
    Trip,
    TripItinerary,
    TripPackage,
    TripPickupLocation,
    TripSchedule,
)
from django_trips.tests import factories

User = get_user_model()


class CommandsTestBase(TestCase):
    """
    Command for creating random trips.
    """

    def setUp(self):
        self.superuser = factories.UserFactory.create(is_superuser=True)
        super().setUp()

    def run_generate_trips_command(self, *args, **kwargs):
        """
        Calls the test command and outputs a dict of the current context.
        """
        out = StringIO()
        call_command('generate_trips', *args, stdout=out, **kwargs)
        out.seek(0)
        return out.read().strip()

    def test_command(self):
        trip_count = 10
        kwargs = {'batch_size': trip_count}
        output = self.run_generate_trips_command(*(), **kwargs)
        self.assertEqual(output.count('Trip Created'), trip_count)

    def test_generated_trips_have_working_region(self):
        """Generated trips' destination/departure should resolve a region,
        not None - this is what the Trips page needs to show a place."""
        self.run_generate_trips_command(batch_size=5)
        for trip in Trip.objects.all():
            self.assertIsNotNone(
                trip.destination.region, f"{trip.destination} has no region"
            )
            self.assertIsNotNone(
                trip.departure.region, f"{trip.departure} has no region"
            )

    def test_generated_trips_have_poster_and_reviews(self):
        """Generated trips should have a poster image and review data,
        not the empty/zero defaults - otherwise trip cards render blank."""
        self.run_generate_trips_command(batch_size=3)
        for trip in Trip.objects.all():
            self.assertTrue(trip.poster_url, f"{trip} has no poster")
            self.assertTrue(trip.reviews.exists(), f"{trip} has no reviews")

    def test_backfills_region_for_preexisting_location(self):
        """
        A Location that already exists (e.g. seeded before this region
        mapping existed, or before this command's first run) but has no
        parent should get backfilled the next time it's touched, not left
        with a permanently None region.

        Calls Command.get_or_create_location directly (rather than running
        the full batch and relying on it randomly picking "Karachi") so
        this test is deterministic.
        """
        preexisting = Location.objects.create(
            name="Karachi", slug=slugify("Karachi")
        )
        self.assertIsNone(preexisting.region)

        Command().get_or_create_location("Karachi")

        preexisting.refresh_from_db()
        self.assertIsNotNone(preexisting.parent)
        self.assertEqual(preexisting.region, "Sindh")

    def test_raises_without_a_superuser(self):
        """The command requires a superuser to attribute generated trips to."""
        User.objects.filter(is_superuser=True).delete()
        with self.assertRaises(CommandError) as ctx:
            call_command("generate_trips", batch_size=1)
        self.assertIn("No superuser found", str(ctx.exception))

    def test_wraps_unexpected_errors_in_command_error(self):
        """An error mid-generation should surface as a CommandError, not crash."""
        with patch.object(
            Command, "create_trip", side_effect=ValueError("boom")
        ):
            with self.assertRaises(CommandError) as ctx:
                self.run_generate_trips_command(batch_size=1)
        self.assertIn("Error creating trip", str(ctx.exception))

    def test_get_region_for_location_returns_none_when_unmapped(self):
        """A location name not present in TRIP_LOCATIONS_BY_REGION has no region."""
        self.assertIsNone(Command().get_region_for_location("Nowhereville"))

    def test_create_reviews_returns_none_without_verified_reviews(self):
        """create_reviews() should skip building a TripReviewSummary when
        every generated review happens to be unverified."""
        trip = factories.TripFactory(trip_schedule=None)
        with patch("django_trips.management.commands.generate_trips.random") as mock_random:
            mock_random.randint.return_value = 3
            mock_random.random.return_value = 1.0  # is_verified = random() < 0.8 -> False
            result = Command().create_reviews(trip)
        self.assertIsNone(result)
        self.assertFalse(trip.reviews.filter(is_verified=True).exists())

    def test_default_batch_size_is_ten(self):
        """No --batch_size given should fall back to the documented default of 10."""
        output = self.run_generate_trips_command()
        self.assertEqual(output.count("Trip Created"), 10)

    def test_get_setting_falls_back_to_default_when_unset_in_django_settings(self):
        """TRIP_HOST_TYPES isn't defined in settings.common - get_setting()
        should fall back to DEFAULT_SETTINGS rather than an empty list."""
        self.assertEqual(
            Command().get_setting("TRIP_HOST_TYPES"),
            DEFAULT_SETTINGS["TRIP_HOST_TYPES"],
        )

    def test_get_setting_prefers_django_settings_when_present(self):
        """TRIP_HOSTS *is* defined in settings.common, so it should win over
        the command's own DEFAULT_SETTINGS fallback."""
        self.assertEqual(Command().get_setting("TRIP_HOSTS"), settings.TRIP_HOSTS)

    def test_create_trip_packages_always_includes_standard_tier(self):
        """STANDARD must always be (re)priced, even when no other tier is
        sampled - it's the trip's guaranteed tier and the surcharge anchor."""
        trip = factories.TripFactory(trip_schedule=None, duration=timedelta(days=10))
        with patch("django_trips.management.commands.generate_trips.random") as mock_random:
            mock_random.randint.side_effect = [8000, 0]  # per_day_rate, then 0 other tiers
            mock_random.sample.return_value = []
            standard_price = Command().create_trip_packages(trip)

        packages = TripPackage.objects.filter(trip=trip)
        self.assertEqual(packages.count(), 1)
        standard = packages.get(name=PackageTier.STANDARD)
        self.assertEqual(standard.base_price, 80000)
        self.assertEqual(standard_price, 80000)

    def test_create_trip_packages_prices_tiers_relative_to_standard(self):
        """BUDGET/PREMIUM prices should scale off the same base as STANDARD
        per TIER_PRICE_FACTORS, and stay ordered budget < standard < premium."""
        trip = factories.TripFactory(trip_schedule=None, duration=timedelta(days=10))
        with patch("django_trips.management.commands.generate_trips.random") as mock_random:
            mock_random.randint.side_effect = [8000, 2]  # per_day_rate, then both other tiers
            mock_random.sample.return_value = [PackageTier.BUDGET, PackageTier.PREMIUM]
            standard_price = Command().create_trip_packages(trip)

        budget = TripPackage.objects.get(trip=trip, name=PackageTier.BUDGET)
        standard = TripPackage.objects.get(trip=trip, name=PackageTier.STANDARD)
        premium = TripPackage.objects.get(trip=trip, name=PackageTier.PREMIUM)

        self.assertEqual(budget.base_price, 60000)
        self.assertEqual(standard.base_price, 80000)
        self.assertEqual(premium.base_price, 116000)
        self.assertEqual(standard_price, 80000)
        self.assertLess(budget.base_price, standard.base_price)
        self.assertLess(standard.base_price, premium.base_price)
        self.assertEqual(
            budget.base_child_price, round(int(budget.base_price) * 0.6 / 100) * 100
        )

    def test_create_schedules_creates_five_schedules_with_expected_statuses(self):
        """create_schedules() should always lay down exactly one expired/FULL
        schedule, one in-progress/PUBLISHED schedule, and three upcoming/
        PUBLISHED schedules."""
        trip = factories.TripFactory(
            trip_schedule=None,
            duration=timedelta(days=7),
            departure=factories.LocationFactory(name="Lahore"),
        )
        Command().create_schedules(trip, base_price=50000)

        schedules = list(TripSchedule.objects.filter(trip=trip).order_by("start_date"))
        self.assertEqual(len(schedules), 5)

        now = timezone.now().date()
        expired, in_progress, *upcoming = schedules

        self.assertEqual(expired.status, ScheduleStatus.FULL)
        self.assertLess(expired.end_date, now)

        self.assertEqual(in_progress.status, ScheduleStatus.PUBLISHED)
        self.assertLess(in_progress.start_date, now)
        self.assertGreater(in_progress.end_date, now)

        self.assertEqual(len(upcoming), 3)
        for schedule in upcoming:
            self.assertEqual(schedule.status, ScheduleStatus.PUBLISHED)
            self.assertGreater(schedule.start_date, now)

    def test_create_schedules_surcharge_matches_peak_weekday_rule(self):
        """Only Thu/Fri/Sat departures should carry a surcharge; every other
        weekday must be surcharge-free, with the child surcharge always a
        60% fraction of the adult one."""
        trip = factories.TripFactory(
            trip_schedule=None,
            duration=timedelta(days=7),
            departure=factories.LocationFactory(name="Lahore"),
        )
        Command().create_schedules(trip, base_price=100000)

        for schedule in TripSchedule.objects.filter(trip=trip):
            if schedule.start_date.weekday() in Command.PEAK_WEEKDAYS:
                self.assertGreater(schedule.additional_price, 0)
                self.assertEqual(
                    schedule.additional_child_price,
                    round(int(schedule.additional_price) * 0.6 / 100) * 100,
                )
            else:
                self.assertEqual(schedule.additional_price, 0)
                self.assertEqual(schedule.additional_child_price, 0)

    def test_create_schedules_creates_pickup_location_at_departure_for_each_schedule(self):
        """Every schedule create_schedules() makes should get a free pickup
        point at the trip's own departure city."""
        trip = factories.TripFactory(
            trip_schedule=None,
            duration=timedelta(days=5),
            departure=factories.LocationFactory(name="Lahore"),
        )
        Command().create_schedules(trip, base_price=40000)

        for schedule in TripSchedule.objects.filter(trip=trip):
            self.assertTrue(
                TripPickupLocation.objects.filter(
                    schedule=schedule, location=trip.departure, additional_price=0
                ).exists()
            )

    def test_create_pickup_locations_always_includes_departure_at_zero_price(self):
        """The departure city pickup point is mandatory and free; 0-2 named
        extra stops may be layered on top."""
        schedule = factories.TripScheduleFactory()
        departure = factories.LocationFactory(name="Lahore")

        Command().create_pickup_locations(schedule, departure)

        pickups = TripPickupLocation.objects.filter(schedule=schedule)
        self.assertTrue(pickups.filter(location=departure, additional_price=0).exists())
        self.assertGreaterEqual(pickups.count(), 1)
        self.assertLessEqual(pickups.count(), 3)

    def test_get_or_create_pickup_point_is_idempotent_child_of_departure(self):
        """A named pickup point should be a Location child of `departure`,
        and re-requesting the same name shouldn't create a duplicate."""
        departure = factories.LocationFactory(name="Lahore")

        first = Command().get_or_create_pickup_point(departure, "Metro Station")
        second = Command().get_or_create_pickup_point(departure, "Metro Station")

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(first.parent, departure)
        self.assertEqual(Location.objects.filter(parent=departure).count(), 1)

    def test_create_itineraries_creates_sequential_days(self):
        """Itinerary day_index should run 1..no_of_days in order, and each
        day's end_time should come after its start_time."""
        trip = factories.TripFactory(trip_schedule=None)
        Command().create_itineraries(trip, no_of_days=4)

        itineraries = list(TripItinerary.objects.filter(trip=trip).order_by("day_index"))
        self.assertEqual([itinerary.day_index for itinerary in itineraries], [1, 2, 3, 4])
        for itinerary in itineraries:
            self.assertGreater(itinerary.end_time, itinerary.start_time)

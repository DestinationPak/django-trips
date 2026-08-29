from datetime import timedelta
from unittest.mock import ANY

import ddt
import pytest
from django.urls import reverse
from django.utils import timezone

from django_trips.choices import PackageTier, ScheduleStatus
from django_trips.models import Trip
from django_trips.tests.factories import (AuthenticatedUserTestCase,
                                          CategoryFactory, HostFactory,
                                          LocationFactory, TripFactory,
                                          TripImageFactory,
                                          TripPickupLocationFactory,
                                          TripScheduleFactory)


@ddt.ddt
@pytest.mark.django_db
class TestTripListAPI(AuthenticatedUserTestCase):
    maxDiff = None
    url = reverse("trips-api:trip-list")

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.trip = TripFactory.create(
            locations=["Lahore", "Gilgit"],
            facilities=["Transport", "Food"],
            gear=["Backpack", "Glasses"],
            categories=["Outdoors", "Hiking"],
        )
        date_in_past = timezone.now() - timedelta(days=7)
        cls.trip_schedule = TripScheduleFactory(trip=cls.trip, start_date=date_in_past)

    def get_trips_list_result(self):
        """Get trip list by calling api and return results"""
        response = self.client.get(self.url, {}, headers=self.headers)
        return response.json()["results"]

    def test_without_authentication(self):
        """
        Verify that trip listing is public - no authentication required.
        """
        response = self.client.get(self.url, {}, headers={})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["results"]), 1)

    def test_trip_list_pagination(self):
        """
        Verify if the returned data has expected pagination keys
        """
        expected_keys = ["count", "results", "next", "previous"]
        response = self.client.get(self.url, {}, headers=self.headers)
        pagination_keys = response.json()
        self.assertTrue(
            all([expected_key in pagination_keys for expected_key in expected_keys]),
            pagination_keys,
        )

    def test_trip_list_results(self):
        """Verify if the returned data contains expected result keys"""
        expected_keys = [
            "name",
            "slug",
            "description",
            "duration",
            "country",
            "categories",
            "featured",
            "trip_url",
            "host",
            "schedules",
        ]
        results = self.get_trips_list_result()
        self.assertEqual(len(results), 1)

        result_keys = results[0].keys()
        self.assertTrue(
            all([expected_key in result_keys for expected_key in expected_keys])
        )

    def test_filter_inactive_trips(self):
        """Verify inactive trips are not returned in api call"""
        TripFactory(is_active=False)
        trips = self.get_trips_list_result()
        self.assertEqual(len(trips), 1)

    def test_schedules_only_include_upcoming_published_departures(self):
        """
        Mirrors the same rule on the detail endpoint - a list card's
        `schedules` should only ever contain what's actually bookable, and
        (unlike the detail endpoint) never a `pickup_locations` key - that's
        booking-flow detail, needlessly heavy to prefetch for every card.
        """
        now = timezone.now()
        upcoming_published = TripScheduleFactory(
            trip=self.trip,
            status=ScheduleStatus.PUBLISHED,
            start_date=(now + timedelta(days=10)).date(),
            end_date=(now + timedelta(days=15)).date(),
            available_seats=12,
            booked_seats=5,
        )
        TripPickupLocationFactory(schedule=upcoming_published, additional_price=750)

        # Neither of these should surface.
        TripScheduleFactory(
            trip=self.trip,
            status=ScheduleStatus.DRAFT,
            start_date=(now + timedelta(days=20)).date(),
            end_date=(now + timedelta(days=25)).date(),
        )
        TripScheduleFactory(
            trip=self.trip,
            status=ScheduleStatus.PUBLISHED,
            start_date=(now - timedelta(days=20)).date(),
            end_date=(now - timedelta(days=15)).date(),
        )

        result = self.get_trips_list_result()[0]
        # cls.trip_schedule (set up in setUpTestData) has a past start_date,
        # so it's excluded regardless of its (randomized) status - only
        # upcoming_published should show up.
        schedule_ids = {schedule["id"] for schedule in result["schedules"]}
        self.assertEqual(schedule_ids, {upcoming_published.id})

        returned_schedule = result["schedules"][0]
        self.assertEqual(returned_schedule["seats_left"], 7)
        self.assertNotIn("pickup_locations", returned_schedule)

    @pytest.mark.skip(reason="Move this to trip detail")
    def test_api_trip_detail_data(self):
        def get_location_data(loc):
            return {
                "type": loc.get_type_display(),
                "name": loc.name,
                "slug": loc.slug,
                "travel_tips": loc.travel_tips,
                "lat": loc.lat,
                "lon": loc.lon,
                "importance": str(loc.importance),
                "is_active": loc.is_active,
            }

        trip_obj = self.trip
        trip_data = self.get_trips_list_result()[0]
        self.assertEqual(trip_data["name"], trip_obj.name)
        self.assertEqual(trip_data["slug"], trip_obj.slug)
        self.assertEqual(trip_data["description"], trip_obj.description)
        self.assertEqual(trip_data["duration"], str(trip_obj.duration))
        self.assertEqual(trip_data["overview"], trip_obj.overview)
        self.assertEqual(trip_data["included"], trip_obj.included)
        self.assertEqual(trip_data["excluded"], trip_obj.excluded)
        self.assertEqual(trip_data["add_ons"], trip_obj.add_ons)
        self.assertEqual(trip_data["travel_tips"], trip_obj.travel_tips)
        self.assertEqual(trip_data["requirements"], trip_obj.requirements)
        self.assertEqual(trip_data["child_policy"], trip_obj.child_policy)
        self.assertEqual(
            trip_data["facilities"],
            [
                {"id": ANY, "name": "Food", "slug": "food", "is_active": ANY},
                {"id": ANY, "name": "Transport", "slug": "transport", "is_active": ANY},
            ],
        )

        self.assertEqual(
            trip_data["gear"],
            [
                {"id": ANY, "name": "Backpack", "slug": "backpack", "is_active": ANY},
                {"id": ANY, "name": "Glasses", "slug": "glasses", "is_active": ANY},
            ],
        )

        self.assertEqual(trip_data["passenger_limit_min"], trip_obj.passenger_limit_min)
        self.assertEqual(trip_data["passenger_limit_max"], trip_obj.passenger_limit_max)
        self.assertEqual(trip_data["age_limit"], trip_obj.age_limit)

        # Location-related
        self.assertEqual(
            trip_data["departure"],
            get_location_data(trip_obj.departure),
        )
        self.assertEqual(
            trip_data["destination"], get_location_data(trip_obj.destination)
        )
        self.assertEqual(
            trip_data["locations"],
            [get_location_data(loc) for loc in trip_obj.locations.all()],
        )

        # Country
        self.assertEqual(trip_data["country"], "PK")

        # Categories
        self.assertEqual(
            trip_data["categories"],
            [
                {
                    "name": cat.name,
                    "slug": cat.slug,
                    "is_active": cat.is_active,
                }
                for cat in trip_obj.categories.all()
            ],
        )

        # Misc fields
        self.assertEqual(trip_data["metadata"], trip_obj.metadata)
        self.assertEqual(trip_data["featured"], trip_obj.featured)
        self.assertEqual(trip_data["is_pax_required"], trip_obj.is_pax_required)
        self.assertEqual(trip_data["is_active"], trip_obj.is_active)

        # Datetime fields
        self.assertIsNotNone(trip_data["created_at"])
        self.assertIsNotNone(trip_data["updated_at"])

        # Host info
        self.assertEqual(trip_data["host"]["name"], trip_obj.host.name)
        self.assertEqual(trip_data["host"]["slug"], trip_obj.host.slug)
        self.assertEqual(trip_data["host"]["description"], trip_obj.host.description)
        self.assertIsNotNone(trip_data["host"]["cancellation_policy"])
        self.assertIsNotNone(trip_data["host"]["verified"])
        self.assertIsNotNone(trip_data["host"]["type"])
        self.assertIsNotNone(trip_data["host"]["rating"])

        # Trip-specific
        self.assertEqual(trip_data["tags"], [])
        self.assertEqual(trip_data["trip_url"], trip_obj.get_absolute_url())

        # Remaining related fields
        self.assertIsNotNone(trip_data["trip_itinerary"])
        self.assertIsNotNone(trip_data["cancellation_policy"])


@ddt.ddt
@pytest.mark.django_db
class TestTripListFiltersAPI(AuthenticatedUserTestCase):
    """Covers the destination/duration/category/price/date filters and ordering on /trips/."""

    maxDiff = None
    url = reverse("trips-api:trip-list")

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.hunza = LocationFactory(name="Hunza")
        cls.skardu = LocationFactory(name="Skardu")
        cls.hiking = CategoryFactory(name="Hiking")
        cls.honeymoon = CategoryFactory(name="Honeymoon")

        cls.trip_hunza = TripFactory(
            name="Hunza Adventure",
            destination=cls.hunza,
            duration=timedelta(days=5),
            categories=[cls.hiking],
        )
        cls.trip_skardu = TripFactory(
            name="Skardu Explorer",
            destination=cls.skardu,
            duration=timedelta(days=10),
            categories=[cls.honeymoon],
        )

        cls.set_standard_price(cls.trip_hunza, 15000)
        cls.set_standard_price(cls.trip_skardu, 30000)

        cls.now = timezone.now().date()
        TripScheduleFactory(
            trip=cls.trip_hunza,
            start_date=cls.now + timedelta(days=5),
            end_date=cls.now + timedelta(days=10),
            status=ScheduleStatus.PUBLISHED,
        )
        TripScheduleFactory(
            trip=cls.trip_skardu,
            start_date=cls.now + timedelta(days=15),
            end_date=cls.now + timedelta(days=25),
            status=ScheduleStatus.PUBLISHED,
        )

    @staticmethod
    def set_standard_price(trip, base_price):
        """Price now lives on the package, not the schedule - set the
        auto-created Standard package's base_price to a known value so
        price filter/ordering tests have deterministic data to assert on."""
        package = trip.packages.get(name=PackageTier.STANDARD)
        package.base_price = base_price
        package.save()

    def get_results(self, params=None):
        response = self.client.get(self.url, params, headers=self.headers)
        self.assertEqual(response.status_code, 200, response.json())
        return response.json()["results"]

    def test_filter_by_destination(self):
        """Previously broken/untested: field_name pointed at a non-existent `trip` relation."""
        data = self.get_results({"destination": self.hunza.slug})
        self.assertEqual({t["name"] for t in data}, {"Hunza Adventure"})

    def test_filter_by_duration_range(self):
        """Previously broken/untested: NumberFilter can't compare against a DurationField."""
        data = self.get_results({"duration_from": 8, "duration_to": 12})
        self.assertEqual({t["name"] for t in data}, {"Skardu Explorer"})

    def test_filter_by_category(self):
        data = self.get_results({"category": self.honeymoon.slug})
        self.assertEqual({t["name"] for t in data}, {"Skardu Explorer"})

    def test_filter_by_verified_host(self):
        """Both fixture trips have verified hosts, so ?verified_host=true is a no-op here -
        the meaningful case is that an unverified host's trip stays excluded (below)."""
        TripFactory(name="Unverified Trip", host=HostFactory(verified=False))
        data = self.get_results({"verified_host": "true"})
        self.assertEqual(
            {t["name"] for t in data}, {"Hunza Adventure", "Skardu Explorer"}
        )

    def test_filter_by_unverified_host(self):
        """An unverified host's trips are excluded from the public catalog outright
        (Trip.objects.active()), so ?verified_host=false can never surface anything here."""
        TripFactory(name="Unverified Trip", host=HostFactory(verified=False))
        data = self.get_results({"verified_host": "false"})
        self.assertEqual({t["name"] for t in data}, set())

    def test_filter_by_price_range(self):
        data = self.get_results({"price_from": 20000})
        self.assertEqual({t["name"] for t in data}, {"Skardu Explorer"})

    def test_filter_by_date_from(self):
        data = self.get_results(
            {"date_from": (self.now + timedelta(days=14)).isoformat()}
        )
        self.assertEqual({t["name"] for t in data}, {"Skardu Explorer"})

    def test_ordering_by_price_ascending(self):
        data = self.get_results({"ordering": "price"})
        names = [t["name"] for t in data]
        self.assertEqual(names, ["Hunza Adventure", "Skardu Explorer"])

    def test_ordering_by_price_descending(self):
        data = self.get_results({"ordering": "-price"})
        names = [t["name"] for t in data]
        self.assertEqual(names, ["Skardu Explorer", "Hunza Adventure"])

    def test_no_duplicate_rows_from_multi_category_join(self):
        """A trip matching >1 filtered category shouldn't be duplicated by the join fan-out."""
        TripFactory(name="Multi Category Trip", categories=[self.hiking, self.honeymoon])
        data = self.get_results(
            {"category": f"{self.hiking.slug},{self.honeymoon.slug}"}
        )
        matched = [t for t in data if t["name"] == "Multi Category Trip"]
        self.assertEqual(len(matched), 1)

    def test_price_match_still_requires_a_bookable_schedule(self):
        """
        Price now lives on the package (date-independent), so a price filter
        can no longer be defeated by a schedule mismatch the way it could
        under the old schedule-scoped pricing model - but a price match
        alone still shouldn't surface a trip with no bookable schedule at
        all (Phase A6's confirmed decision).
        """
        trip = TripFactory(
            name="Unbookable Cheap Trip", destination=self.hunza, trip_schedule=None
        )
        self.set_standard_price(trip, 15000)
        TripScheduleFactory(
            trip=trip,
            start_date=self.now + timedelta(days=5),
            end_date=self.now + timedelta(days=10),
            status=ScheduleStatus.DRAFT,
        )
        data = self.get_results({"price_from": 10000, "price_to": 20000})
        self.assertNotIn("Unbookable Cheap Trip", {t["name"] for t in data})

    def test_price_and_date_constraints_are_independent(self):
        """
        Unlike the old schedule-scoped pricing model, a trip's package price
        and its schedule's date are unrelated - a trip should match a price
        filter and a date filter together even when satisfying them doesn't
        require the same schedule row (there's only ever one base_price per
        package anyway, so this is now the expected/correct behavior rather
        than the "leaky join" the old combined-Q design guarded against).
        """
        data = self.get_results(
            {
                "price_from": 10000,
                "price_to": 20000,
                "date_from": (self.now + timedelta(days=1)).isoformat(),
            }
        )
        self.assertEqual({t["name"] for t in data}, {"Hunza Adventure"})

    def test_empty_query_returns_all_active_trips(self):
        data = self.get_results()
        self.assertEqual(len(data), Trip.objects.active().count())


@pytest.mark.django_db
class TestTripListQueryCount(AuthenticatedUserTestCase):
    """
    Pins the list endpoint's query count so a future change can't quietly
    reintroduce an N+1 without a test failing.

    `TripViewSet.get_queryset` `select_related`s every single-valued
    relation `TripListSerializer` touches (`destination`, `destination.parent`,
    `review_summary`, `host` -> `host.type`/`host.ratings`) and
    `prefetch_related`s every multi-valued one (`schedules`, `images`,
    `categories`, `facilities`, `trust_badges`), plus `packages`/`reviews` via
    a `Prefetch(..., to_attr=...)` that `get_starting_price`/
    `get_trip_review_summary_data` read from instead of re-querying. The two
    assertions below prove that actually holds: a second trip (with its own
    schedule + gallery) adds zero extra queries, because every per-trip
    relation now resolves from an `IN (...)` batch fetched once for the whole
    page rather than once per row.

    11 is today's fixed overhead (auth, the paginator's count, the main
    row query, and one batch query per prefetched relation) - if a future
    field adds a genuinely new relation, update both constants together and
    keep them equal; if only one changes, that's this test catching a
    regression back to N+1.
    """

    url = reverse("trips-api:trip-list")

    def make_trip_with_gallery(self, image_count=2):
        """A trip with a bookable schedule (so it's a realistic list-page
        row) and a small photo gallery (so `images` has something to fetch)."""
        trip = TripFactory(trip_schedule=None)
        TripScheduleFactory(
            trip=trip,
            start_date=timezone.now().date() + timedelta(days=5),
            end_date=timezone.now().date() + timedelta(days=10),
            status=ScheduleStatus.PUBLISHED,
        )
        TripImageFactory.create_batch(image_count, trip=trip)
        return trip

    def test_query_count_does_not_scale_with_trip_count(self):
        self.make_trip_with_gallery()
        with self.assertNumQueries(11):
            self.client.get(self.url, {}, headers=self.headers)

        self.make_trip_with_gallery()
        with self.assertNumQueries(11):
            self.client.get(self.url, {}, headers=self.headers)

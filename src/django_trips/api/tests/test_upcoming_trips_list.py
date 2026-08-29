from datetime import timedelta
from unittest.mock import ANY

import ddt
import factory
import pytest
from django.core.files.base import ContentFile
from django.urls import reverse
from django.utils import timezone

from django_trips.choices import LocationType, PackageTier
from django_trips.models import TripSchedule
from django_trips.tests.factories import (AuthenticatedUserTestCase,
                                          LocationFactory, TripFactory,
                                          TripScheduleFactory)

current_time = timezone.now().date()
seven_days_ago = current_time - timedelta(days=7)


@ddt.ddt
@pytest.mark.django_db
class TestUpcomingTripsListAPI(AuthenticatedUserTestCase):
    maxDiff = None
    url = reverse("trips-api:upcoming-trips-list")

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

        destinations = [
            LocationFactory(name="Swat"),
            LocationFactory(name="Hunza"),
            LocationFactory(name="Skardu"),
        ]
        departure_locations = [
            LocationFactory(name="Islamabad"),
            LocationFactory(name="Lahore"),
            LocationFactory(name="Jhelum"),
        ]
        cls.trips = TripFactory.create_batch(
            size=10,
            # Trip 1, Trip 2, Trip 10.
            name=factory.Iterator([f"Trip {i}" for i in range(1, 11)]),
            # 4 days -- 13 days
            duration=factory.Iterator([timedelta(days=i + 3) for i in range(1, 11)]),
            destination=factory.Iterator(destinations),
            departure=factory.Iterator(departure_locations),
        )

        # Trip 1, Trip 2: schedule fully in the past -> never "upcoming".
        for i, trip in enumerate(cls.trips[:2]):
            cls.set_package_price(trip, 10000)
            TripScheduleFactory(
                trip=trip,
                start_date=seven_days_ago + timedelta(days=i),
                end_date=seven_days_ago + timedelta(days=i + 3),
                additional_price=0,
            )

        # Trip 3, Trip 4: already started (start in the past, end in the
        # future) -- "in progress today", but NOT "upcoming" since it has
        # already started.
        for i, trip in enumerate(cls.trips[2:4]):
            cls.set_package_price(trip, 12000)
            TripScheduleFactory(
                trip=trip,
                start_date=current_time - timedelta(days=i + 1),
                end_date=current_time + timedelta(days=10 + i),
                additional_price=0,
            )

        # Trip 5 -- Trip 10: genuinely upcoming (start AND end in the
        # future) -- the 6 trips returned by an empty/default query, with a
        # price gradient (14,000 -- 19,000) for the price_from/price_to
        # assertions below.
        cls.upcoming_start_dates = [
            current_time + timedelta(days=i + 1) for i in range(6)
        ]
        cls.upcoming_end_dates = [
            current_time + timedelta(days=i + 10) for i in range(6)
        ]
        base_price = 13000
        for i, trip in enumerate(cls.trips[4:]):
            base_price += 1000
            cls.set_package_price(trip, base_price)
            TripScheduleFactory(
                trip=trip,  # Trip 5 -- Trip 10
                start_date=cls.upcoming_start_dates[i],
                end_date=cls.upcoming_end_dates[i],
                additional_price=0,
            )

    @staticmethod
    def set_package_price(trip, base_price):
        """
        The upcoming-trips endpoint's "price" (ordering/price_from/price_to)
        is trip_min_base_price + schedule.additional_price (Phase A8), not a
        raw schedule field anymore. Setting the package's base_price and
        zeroing the schedule's surcharge lands each trip at exactly this
        price, so the gradient the tests below assert on is unchanged.
        """
        package = trip.packages.get(name=PackageTier.STANDARD)
        package.base_price = base_price
        package.save()

    @staticmethod
    def get_resolved_price(schedule_id):
        """
        The same trip_min_base_price + additional_price value the view
        annotates as `price` (Phase A8) - not a literal field in the JSON
        response (TripScheduleBaseSerializer only exposes additional_price/
        additional_child_price), so tests that need to assert on it look it
        up directly instead of reading a `price` key off the response body.
        """
        schedule = TripSchedule.objects.get(pk=schedule_id)
        package = schedule.trip.packages.order_by("base_price").first()
        return package.base_price + schedule.additional_price

    def get_trips_list_result(self, params=None, expected_code=200):
        """Get trip list by calling api and return results"""
        response = self.client.get(self.url, params, headers=self.headers)
        self.assertEqual(response.status_code, expected_code, response.json())
        return response.json()["results"]

    @ddt.data(
        *(
            ("Trip 1", 1),  # substring-matches both "Trip 1" (excluded) and "Trip 10" (included)
            ("Trip 2", 0),
            ("Trip 3", 0),
            ("Trip 4", 0),
            ("Trip 5", 1),
            ("Trip 6", 1),
            ("Trip 7", 1),
            ("Trip 8", 1),
            ("Trip 9", 1),
            ("Trip 10", 1),
            ("Trip", 6),  # partial match
            ("trip", 6),  # case-insensitive
            ("Invalid", 0),  # no match
        )
    )
    @ddt.unpack
    def test_filter_by_name(self, search, expected_count):
        """Should return trips matching name (case-insensitive contains)"""
        data = self.get_trips_list_result({"name": search})
        self.assertEqual(len(data), expected_count, search)

    @ddt.data(
        *(
            (10000, 6),
            (11500, 6),
            (13000, 6),
            (14000, 6),
            (15000, 5),
            (16000, 4),
            (17000, 3),
            (18000, 2),
            (19000, 1),
            (20000, 0),
            (21000, 0),
        )
    )
    @ddt.unpack
    def test_filter_by_price_from(self, price, expected_count):
        """Should return trips with price >= price_from"""
        data = self.get_trips_list_result({"price_from": price})
        self.assertEqual(len(data), expected_count, price)

    @ddt.data(
        *(
            (10000, 0),
            (11500, 0),
            (13000, 0),
            (14000, 1),
            (15000, 2),
            (16000, 3),
            (17000, 4),
            (18000, 5),
            (19000, 6),
            (20000, 6),
            (21000, 6),
            (25000, 6),
        )
    )
    @ddt.unpack
    def test_filter_by_price_to(self, price, expected_count):
        """Should return trips with price <= price_to"""
        data = self.get_trips_list_result({"price_to": price})
        self.assertEqual(len(data), expected_count, price)

    @ddt.data(
        ("past-mid", current_time - timedelta(days=5)),
        ("future", current_time + timedelta(days=2)),
    )
    @ddt.unpack
    def test_filter_by_date_from(self, label, date):
        """Should return trips starting on/after the given date"""
        expected_slugs = {
            s.trip.slug
            for s in TripSchedule.objects.upcoming().filter(start_date__gte=date)
        }
        data = self.get_trips_list_result({"date_from": date.isoformat()})
        response_slugs = {t["trip"]["slug"] for t in data}
        self.assertSetEqual(response_slugs, expected_slugs, msg=f"{label=} {date=}")

    @ddt.data(
        ("past-limit", current_time - timedelta(days=10), 0),
        ("far-future-limit", current_time + timedelta(days=20), 6),
    )
    @ddt.unpack
    def test_filter_by_date_to(self, label, date, expected_count):
        """Should return trips ending before/equal to date_to"""
        data = self.get_trips_list_result({"date_to": date.isoformat()})
        self.assertEqual(len(data), expected_count, msg=f"{label=} {date=}")

    def test_filter_by_destination(self):
        """Should filter trips by destination name (case-insensitive match)"""
        destinations = [self.trips[2].destination.slug, self.trips[1].destination.slug]
        query_params = {"destination": ",".join(destinations)}
        data = self.get_trips_list_result(query_params)

        response_trips = {item["trip"]["destination"]["slug"] for item in data}
        self.assertTrue(all(t in destinations for t in response_trips))

    def test_filter_by_duration_range(self):
        """Should return trips within duration range"""
        data = self.get_trips_list_result({"duration_from": 5, "duration_to": 8})
        durations = [item["trip"]["duration"] for item in data]
        for d in durations:
            d = int(d[0])
            self.assertGreaterEqual(d, 5)
            self.assertLessEqual(d, 8)

    def test_combined_filters(self):
        """Should apply multiple filters together"""
        query = {
            "price_from": 13000,
            "price_to": 17000,
            "duration_from": 5,
            "duration_to": 10,
        }
        data = self.get_trips_list_result(query)
        resolved_prices = [self.get_resolved_price(t["id"]) for t in data]
        self.assertTrue(all(13000 <= p <= 17000 for p in resolved_prices))
        expected_durations = [f"{d} Days {d - 1} Nights" for d in range(8, 11)]
        actual_durations = [t["trip"]["duration"] for t in data]
        self.assertEqual(actual_durations, expected_durations)

    def test_invalid_date_format(self):
        """Should return 400 for invalid date"""
        response = self.client.get(
            self.url, {"date_from": "not-a-date"}, headers=self.headers
        )
        self.assertEqual(response.status_code, 400)

    def test_empty_query_returns_all(self):
        """Should return all active trips if no filters applied"""
        data = self.get_trips_list_result()
        self.assertEqual(len(data), 6)

    @ddt.data(
        ("price", "price"),
        ("price", "-price"),
        ("start_date", "start_date"),
        ("start_date", "-start_date"),
        ("trip__name", "trip__name"),
        ("trip__name", "-trip__name"),
    )
    @ddt.unpack
    def test_upcoming_trips_ordering(self, field, ordering):
        """Test ordering by various fields."""
        is_reverse = ordering.startswith("-")
        params = {"ordering": ordering}
        data = self.get_trips_list_result(params)

        if field == "price":
            # "price" is the resolved trip_min_base_price + additional_price
            # (Phase A8) - not a literal field in the JSON response.
            response_data = [self.get_resolved_price(r["id"]) for r in data]
        else:
            fields = field.split("__")
            if len(fields) > 1:
                # For fields like 'trip__duration'
                response_data = [r[fields[0]][fields[1]] for r in data]
            else:
                response_data = [r[field] for r in data]

        self.assertEqual(
            response_data,
            sorted(response_data, reverse=is_reverse),
            f"{field} - {is_reverse} - {response_data}",
        )

    @ddt.data(
        ("trip__duration", "trip__duration"),
        ("trip__duration", "-trip__duration"),
    )
    @ddt.unpack
    def test_upcoming_trips_ordering_by_duration(self, field, ordering):
        """Test ordering by trip_duration field."""
        is_reverse = ordering.startswith("-")
        params = {"ordering": ordering}
        data = self.get_trips_list_result(params)

        fields = field.split("__")
        field_data = [int(r[fields[0]][fields[1]].split(" ")[0]) for r in data]

        self.assertEqual(
            field_data,
            sorted(field_data, reverse=is_reverse),
            f"Ordering by {field} (reverse={is_reverse}) failed! Result: {field_data}",
        )

    def test_without_authentication(self):
        """Verify upcoming trips listing is public - no authentication required."""
        response = self.client.get(self.url, {}, headers={})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["results"]), 6)

    def test_destinations_without_authentication(self):
        """Verify the destinations endpoint is public - no authentication required."""
        url = reverse("trips-api:destinations")
        response = self.client.get(url, {}, headers={})
        self.assertEqual(response.status_code, 200)

    def test_destinations_include_region(self):
        """Each destination should report its region, derived from its parent."""
        province = LocationFactory(name="Sindh Region", type=LocationType.PROVINCE)
        karachi_beach = LocationFactory(
            name="Karachi Beach", type=LocationType.CITY, parent=province
        )
        TripFactory(destination=karachi_beach)

        url = reverse("trips-api:destinations")
        response = self.client.get(url, {}, headers=self.headers)
        destinations = {d["name"]: d for d in response.json()["results"]}
        self.assertEqual(destinations["Karachi Beach"]["region"], "Sindh Region")

    def test_destinations_exclude_locations_with_no_trips(self):
        """A location that is never a trip's destination shouldn't appear in the dropdown."""
        LocationFactory(name="Unused Waypoint")

        url = reverse("trips-api:destinations")
        response = self.client.get(url, {}, headers=self.headers)
        names = {d["name"] for d in response.json()["results"]}
        self.assertNotIn("Unused Waypoint", names)

    def test_destinations_ordered_by_trips_count_descending(self):
        """Destinations should be ordered by their active trip count, most first."""
        quiet = LocationFactory(name="Quiet Valley")
        popular = LocationFactory(name="Popular Peak")
        TripFactory(destination=quiet)
        TripFactory.create_batch(3, destination=popular)

        url = reverse("trips-api:destinations")
        response = self.client.get(url, {}, headers=self.headers)
        results = {d["name"]: d for d in response.json()["results"]}
        self.assertEqual(results["Popular Peak"]["trips_count"], 3)
        self.assertEqual(results["Quiet Valley"]["trips_count"], 1)

        names = [d["name"] for d in response.json()["results"]]
        self.assertLess(names.index("Popular Peak"), names.index("Quiet Valley"))

    def test_destinations_trips_count_excludes_inactive_trips(self):
        """trips_count should only count active trips against this destination."""
        destination = LocationFactory(name="Mixed Activity Town")
        TripFactory.create_batch(2, destination=destination, is_active=True)
        TripFactory(destination=destination, is_active=False)

        url = reverse("trips-api:destinations")
        response = self.client.get(url, {}, headers=self.headers)
        results = {d["name"]: d for d in response.json()["results"]}
        self.assertEqual(results["Mixed Activity Town"]["trips_count"], 2)

    def test_destination_poster_from_url(self):
        """A destination's poster should reflect poster_url when set."""
        destination = LocationFactory(
            name="Poster Town", poster_url="https://example.com/poster-town.jpg"
        )
        TripFactory(destination=destination)

        url = reverse("trips-api:destinations")
        response = self.client.get(url, {}, headers=self.headers)
        results = {d["name"]: d for d in response.json()["results"]}
        self.assertEqual(
            results["Poster Town"]["poster"], "https://example.com/poster-town.jpg"
        )

    def test_destination_poster_none_when_unset(self):
        """A destination's poster should be None (not crash) when unset."""
        destination = LocationFactory(name="Posterless Town", poster_url=None)
        TripFactory(destination=destination)

        url = reverse("trips-api:destinations")
        response = self.client.get(url, {}, headers=self.headers)
        results = {d["name"]: d for d in response.json()["results"]}
        self.assertIsNone(results["Posterless Town"]["poster"])

    def test_destination_poster_prefers_upload_over_url(self):
        """A destination's poster should resolve poster_image over poster_url when both are set."""
        destination = LocationFactory(
            name="Uploaded Poster Town",
            poster_url="https://example.com/external.jpg",
        )
        destination.poster_image.save(
            "poster.jpg", ContentFile(b"fake-image-bytes"), save=True
        )
        self.addCleanup(destination.poster_image.delete, save=False)
        TripFactory(destination=destination)

        url = reverse("trips-api:destinations")
        response = self.client.get(url, {}, headers=self.headers)
        results = {d["name"]: d for d in response.json()["results"]}
        poster = results["Uploaded Poster Town"]["poster"]
        self.assertNotEqual(poster, "https://example.com/external.jpg")
        self.assertIn("poster.jpg", poster)

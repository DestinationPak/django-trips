from datetime import timedelta

from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from django_trips.choices import ScheduleStatus
from django_trips.models import CancellationPolicy
from django_trips.tests.factories import (AuthenticatedUserTestCase,
                                          CategoryFactory, FacilityFactory,
                                          GearFactory, HostFactory,
                                          LocationFactory, TripFactory,
                                          TripItineraryFactory,
                                          TripPackageFactory,
                                          TripPickupLocationFactory,
                                          TripScheduleFactory)


class TripRetrieveTestCase(AuthenticatedUserTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.trip = TripFactory(
            locations=["Lahore", "Gilgit"],
            facilities=["Transport", "Food"],
            gear=["Backpack", "Glasses"],
            categories=["Outdoors", "Hiking"],
        )
        cls.package1 = TripPackageFactory(trip=cls.trip, name="Deluxe")
        cls.package2 = TripPackageFactory(trip=cls.trip, name="Budget")
        cls.package3 = TripPackageFactory(trip=cls.trip, name="Five Star")
        cls.host = cls.trip.host
        cls.destination = cls.trip.destination
        cls.departure = cls.trip.departure
        cls.trip.locations.add(cls.departure, cls.destination)

        # Add itinerary
        TripItineraryFactory(
            trip=cls.trip,
            day_index=1,
            title="Arrival Day",
            location=cls.departure,
            category=cls.trip.categories.all().first(),
        )

    def make_api_call(self, identifier, expected_status_code=status.HTTP_200_OK):
        url = reverse("trips-api:trip-detail", kwargs={"identifier": identifier})
        response = self.client.get(url, headers=self.headers)
        self.assertEqual(response.status_code, expected_status_code)
        return response.json()

    def test_retrieve_trip_by_id(self):
        data = self.make_api_call(self.trip.id)
        self.assertEqual(data["id"], self.trip.id)
        self.assertEqual(data["name"], self.trip.name)

    def test_retrieve_trip_by_slug(self):
        data = self.make_api_call(self.trip.slug)
        self.assertEqual(data["slug"], self.trip.slug)

    def test_trip_detail_serializer_fields_present(self):
        data = self.make_api_call(self.trip.slug)
        expected_fields = {
            "id",
            "name",
            "slug",
            "description",
            "duration",
            "host",
            "departure",
            "destination",
            "facilities",
            "gear",
            "categories",
            "locations",
            "trip_itinerary",
            "tags",
            "packages",
            "schedules",
            "cancellation_policy",
            "refund_schedule",
        }
        self.assertTrue(expected_fields.issubset(data.keys()))

    def test_refund_schedule_defaults_to_platform_wide_policy(self):
        """No host-level override set on this trip's host, so `refund_schedule`
        falls back to the current `CancellationPolicy.refund_schedule` default."""
        data = self.make_api_call(self.trip.slug)
        platform_default = CancellationPolicy.current().refund_schedule
        self.assertEqual(data["refund_schedule"], platform_default)

    def test_refund_schedule_prefers_host_override(self):
        host_schedule = [{"label": "Custom", "min_hours_before_departure": 24, "refund_percent": 25}]
        self.host.refund_schedule = host_schedule
        self.host.save(update_fields=["refund_schedule"])

        data = self.make_api_call(self.trip.slug)
        self.assertEqual(data["refund_schedule"], host_schedule)

    def test_schedules_only_include_upcoming_published_departures(self):
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

        # Neither of these should surface in the availability picker.
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

        data = self.make_api_call(self.trip.slug)
        schedule_ids = {schedule["id"] for schedule in data["schedules"]}
        self.assertEqual(schedule_ids, {upcoming_published.id})

        returned_schedule = data["schedules"][0]
        self.assertEqual(returned_schedule["seats_left"], 7)
        self.assertEqual(len(returned_schedule["pickup_locations"]), 1)
        self.assertEqual(returned_schedule["pickup_locations"][0]["additional_price"], 750)

    def test_retrieve_nonexistent_trip_returns_404(self):
        self.make_api_call("non-existent-slug", status.HTTP_404_NOT_FOUND)

    def test_retrieve_without_authentication(self):
        """Verify trip retrieval is public - no authentication required."""
        url = reverse("trips-api:trip-detail", kwargs={"identifier": self.trip.slug})
        response = self.client.get(url, headers={})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["slug"], self.trip.slug)

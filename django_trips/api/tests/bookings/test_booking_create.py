from datetime import timedelta
from unittest import mock

import ddt
from django.urls import reverse
from django.utils import timezone

from django_trips.choices import BookingStatus, PackageTier, ScheduleStatus
from django_trips.models import TripBooking
from django_trips.tests.factories import (
    AuthenticatedUserTestCase,
    TripBookingFactory,
    TripFactory,
    TripPackageFactory,
    TripPickupLocationFactory,
    TripScheduleFactory,
)


@ddt.ddt
class TripBookingCreateTestCase(AuthenticatedUserTestCase):
    maxDiff = None

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

        cls.trip = TripFactory.create(
            locations=["Lahore", "Gilgit"],
            facilities=["Transport", "Food"],
            gear=["Backpack", "Glasses"],
            categories=["Outdoors", "Hiking"],
        )
        schedule_date = timezone.now().date() + timedelta(days=7)
        cls.trip_schedule = TripScheduleFactory(
            trip=cls.trip,
            start_date=schedule_date,
            available_seats=20,
            booked_seats=0,
        )
        cls.schedule2 = TripScheduleFactory(
            trip=cls.trip, start_date=timezone.now() + timedelta(days=20)
        )

        cls.url = reverse(
            "trips-api:trip-bookings-create", kwargs={"trip_id": cls.trip.pk}
        )
        cls.payload = {
            "schedule": cls.trip_schedule.id,
            "full_name": "Foo Bar",
            "email": "foo@bar.com",
            "phone_number": "+923331234567",
            "adults": 5,
            "children": 0,
            "target_date": schedule_date.isoformat(),
            "message": "this is a test message",
            "terms_accepted": True,
        }

    def make_create_trip_booking_request(self, data=None, expected_response=201):
        data = data or self.payload
        response = self.client.post(
            self.url, data, headers=self.headers, content_type="application/json"
        )
        self.assertEqual(response.status_code, expected_response, response.json())
        return response.json()

    def test_booking_create(self):
        data = self.make_create_trip_booking_request()
        self.assertTrue("number" in data)
        self.assertTrue("target_date" in data)
        new_booking = TripBooking.objects.get(number=data["number"])

        self.assertDictEqual(
            data,
            {
                "number": mock.ANY,
                "otp": mock.ANY,
                "status": BookingStatus.PENDING,
                "status_events": [],
                "full_name": "Foo Bar",
                "email": "foo@bar.com",
                "phone_number": "+923331234567",
                "adults": 5,
                "children": 0,
                "target_date": f"{new_booking.target_date.date().isoformat()}T00:00:00Z",
                "message": "this is a test message",
                "terms_accepted": True,
                "created_by": self.user.pk,
                "created": mock.ANY,
                "modified": mock.ANY,
                "schedule_details": mock.ANY,
                "package_details": mock.ANY,
                "pickup_location_details": None,
                "total_price": mock.ANY,
            },
        )

    def test_booking_create_returns_generated_otp(self):
        data = self.make_create_trip_booking_request()
        self.assertRegex(data["otp"], r"^\d{4}$")

        new_booking = TripBooking.objects.get(number=data["number"])
        self.assertEqual(new_booking.otp, data["otp"])

    def test_booking_create_rejects_schedule_from_another_trip(self):
        other_trip = TripFactory.create(trip_schedule=None)
        other_schedule = TripScheduleFactory(trip=other_trip)

        data = self.make_create_trip_booking_request(
            {**self.payload, "schedule": other_schedule.id}, expected_response=400
        )
        self.assertIn("schedule", data)

    def test_booking_create_allows_anonymous_guest(self):
        response = self.client.post(
            self.url, self.payload, content_type="application/json"
        )
        self.assertEqual(response.status_code, 201, response.json())
        data = response.json()
        self.assertIsNone(data["created_by"])

        new_booking = TripBooking.objects.get(number=data["number"])
        self.assertIsNone(new_booking.created_by)

    def test_booking_create_increments_booked_seats(self):
        self.trip_schedule.refresh_from_db()
        before = self.trip_schedule.booked_seats

        self.make_create_trip_booking_request()

        self.trip_schedule.refresh_from_db()
        self.assertEqual(
            self.trip_schedule.booked_seats,
            before + self.payload["adults"] + self.payload["children"],
        )

    @ddt.data(False, None)
    def test_booking_create_rejects_without_terms_accepted(self, terms_accepted):
        payload = {**self.payload, "terms_accepted": terms_accepted}
        if terms_accepted is None:
            del payload["terms_accepted"]

        data = self.make_create_trip_booking_request(payload, expected_response=400)
        self.assertIn("terms_accepted", data)

    def test_booking_create_defaults_to_standard_package(self):
        """When no `package` is supplied, the booking should default to the
        trip's (auto-created) Standard package, and its total_price should
        reflect that package's base_price plus the schedule's surcharge."""
        data = self.make_create_trip_booking_request()
        self.assertEqual(data["package_details"]["name"], PackageTier.STANDARD)

        new_booking = TripBooking.objects.get(number=data["number"])
        self.assertEqual(new_booking.package.name, PackageTier.STANDARD)
        expected_total = (
            new_booking.package.base_price + self.trip_schedule.additional_price
        ) * self.payload["adults"]
        self.assertEqual(new_booking.total_price, expected_total)

    def test_booking_create_with_explicit_package_uses_its_base_price(self):
        """An explicitly-supplied package's base_price should be reflected in
        the stored total_price - base_price + schedule surcharge, times persons."""
        package = TripPackageFactory(
            trip=self.trip,
            name=PackageTier.PREMIUM,
            base_price=15000,
            base_child_price=8000,
        )
        data = self.make_create_trip_booking_request(
            {**self.payload, "package": package.id}
        )

        new_booking = TripBooking.objects.get(number=data["number"])
        self.assertEqual(new_booking.package_id, package.id)
        expected_total = (
            package.base_price + self.trip_schedule.additional_price
        ) * self.payload["adults"]
        self.assertEqual(new_booking.total_price, expected_total)

    def test_booking_create_with_children_adds_child_price(self):
        """Children should be priced using the package/schedule's child price,
        not the adult price - and counted towards booked seats too."""
        package = TripPackageFactory(
            trip=self.trip,
            name=PackageTier.PREMIUM,
            base_price=15000,
            base_child_price=8000,
        )
        data = self.make_create_trip_booking_request(
            {**self.payload, "package": package.id, "adults": 2, "children": 3}
        )

        new_booking = TripBooking.objects.get(number=data["number"])
        self.assertEqual(new_booking.adults, 2)
        self.assertEqual(new_booking.children, 3)
        expected_total = (
            package.base_price + self.trip_schedule.additional_price
        ) * 2 + (
            package.base_child_price + self.trip_schedule.additional_child_price
        ) * 3
        self.assertEqual(new_booking.total_price, expected_total)

        self.trip_schedule.refresh_from_db()
        self.assertEqual(self.trip_schedule.booked_seats, 5)

    def test_booking_create_rejects_package_from_another_trip(self):
        other_trip = TripFactory.create(trip_schedule=None)
        other_package = TripPackageFactory(trip=other_trip, name=PackageTier.PREMIUM)

        data = self.make_create_trip_booking_request(
            {**self.payload, "package": other_package.id}, expected_response=400
        )
        self.assertIn("package", data)

    def test_booking_create_with_pickup_location_adds_surcharge(self):
        """A selected pickup point should be saved on the booking and its
        additional_price added to both the adult and child price."""
        pickup = TripPickupLocationFactory(
            schedule=self.trip_schedule, additional_price=500
        )
        data = self.make_create_trip_booking_request(
            {**self.payload, "pickup_location": pickup.id, "adults": 2, "children": 3}
        )
        self.assertEqual(data["pickup_location_details"]["id"], pickup.id)

        new_booking = TripBooking.objects.get(number=data["number"])
        self.assertEqual(new_booking.pickup_location_id, pickup.id)
        expected_total = (
            new_booking.package.base_price
            + self.trip_schedule.additional_price
            + pickup.additional_price
        ) * 2 + (
            new_booking.package.base_child_price
            + self.trip_schedule.additional_child_price
            + pickup.additional_price
        ) * 3
        self.assertEqual(new_booking.total_price, expected_total)

    def test_booking_create_rejects_pickup_location_from_another_schedule(self):
        other_pickup = TripPickupLocationFactory(schedule=self.schedule2)

        data = self.make_create_trip_booking_request(
            {**self.payload, "pickup_location": other_pickup.id},
            expected_response=400,
        )
        self.assertIn("pickup_location", data)

    def test_booking_create_rejects_when_not_enough_seats(self):
        self.trip_schedule.available_seats = 3
        self.trip_schedule.booked_seats = 0
        self.trip_schedule.save()

        data = self.make_create_trip_booking_request(
            {**self.payload, "adults": 5}, expected_response=400
        )
        self.assertIn("adults", data)

        self.trip_schedule.refresh_from_db()
        self.assertEqual(self.trip_schedule.booked_seats, 0)
